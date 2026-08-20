"""Overflow-safe capacity planner for branch-cache sizing (offline / lab)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# Hard ceilings to keep plans finite and reject absurd operator input.
MAX_BITRATE_BPS = 100_000_000  # 100 Mbps per rendition
MAX_RENDITIONS = 16
MAX_PEAK_VIEWERS = 100_000
MAX_WORKING_SET_TITLES = 50_000
MAX_RETENTION_HOURS = 24 * 90
MAX_BYTES = 50 * (1024**4)  # 50 TiB plan ceiling
MAX_HEADROOM_PCT = 500
MAX_REPLICATION = 8


class CapacityPlanError(ValueError):
    def __init__(self, message: str, *, code: str = "invalid_plan") -> None:
        super().__init__(message)
        self.code = code


def _require_int(name: str, value: int, *, min_v: int = 0, max_v: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise CapacityPlanError(f"{name} must be an int", code="type")
    if value < min_v or value > max_v:
        raise CapacityPlanError(f"{name} out of bounds [{min_v}, {max_v}]", code="bounds")
    return value


def _require_float(name: str, value: float, *, min_v: float, max_v: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CapacityPlanError(f"{name} must be a number", code="type")
    f = float(value)
    if f != f or f in {float("inf"), float("-inf")}:  # NaN/inf
        raise CapacityPlanError(f"{name} must be finite", code="finite")
    if f < min_v or f > max_v:
        raise CapacityPlanError(f"{name} out of bounds [{min_v}, {max_v}]", code="bounds")
    return f


def checked_mul(*values: int) -> int:
    """Multiply ints with overflow protection.

    Intermediate products may exceed MAX_BYTES (e.g. headroom percent math);
    callers must still reject final disk recommendations above MAX_BYTES.
    """
    acc = 1
    # Allow intermediates up to MAX_BYTES * MAX_HEADROOM_PCT for percent math.
    limit = MAX_BYTES * max(MAX_HEADROOM_PCT, 8)
    for v in values:
        if v < 0:
            raise CapacityPlanError("negative factor in capacity multiply", code="overflow")
        if v == 0:
            return 0
        if acc > limit // v:
            raise CapacityPlanError("capacity arithmetic overflow", code="overflow")
        acc *= v
    return acc


def bytes_for_bitrate_hour(bitrate_bps: int, hours: float) -> int:
    """Convert bits/sec × hours → bytes (rounded up)."""
    bps = _require_int("bitrate_bps", bitrate_bps, min_v=1, max_v=MAX_BITRATE_BPS)
    h = _require_float("hours", hours, min_v=0.0, max_v=float(MAX_RETENTION_HOURS))
    # bytes = bitrate * hours * 3600 / 8
    bits = checked_mul(bps, int(h * 3600 + 0.999999))
    return (bits + 7) // 8


@dataclass(frozen=True)
class RenditionSpec:
    label: str
    bitrate_bps: int


@dataclass(frozen=True)
class CapacityPlanInput:
    renditions: list[RenditionSpec]
    peak_concurrent_viewers: int
    working_set_titles: int
    avg_title_duration_hours: float
    retention_hours: float
    replication_factor: int = 1
    headroom_percent: int = 30
    expected_hit_ratio: float = 0.75
    high_watermark_ratio: float = 0.90
    low_watermark_ratio: float = 0.70
    min_free_bytes: int = 1_000_000_000
    origin_egress_cap_bps: int | None = None


@dataclass(frozen=True)
class CapacityPlan:
    package_bytes_per_title: int
    working_set_bytes: int
    retention_bytes: int
    replicated_bytes: int
    with_headroom_bytes: int
    recommended_disk_bytes: int
    high_watermark_bytes: int
    low_watermark_bytes: int
    min_free_bytes: int
    peak_origin_bps_on_miss: int
    expected_origin_bps: int
    expected_hit_ratio: float
    safe: bool
    warnings: tuple[str, ...]
    rejection_reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "package_bytes_per_title": self.package_bytes_per_title,
            "working_set_bytes": self.working_set_bytes,
            "retention_bytes": self.retention_bytes,
            "replicated_bytes": self.replicated_bytes,
            "with_headroom_bytes": self.with_headroom_bytes,
            "recommended_disk_bytes": self.recommended_disk_bytes,
            "high_watermark_bytes": self.high_watermark_bytes,
            "low_watermark_bytes": self.low_watermark_bytes,
            "min_free_bytes": self.min_free_bytes,
            "peak_origin_bps_on_miss": self.peak_origin_bps_on_miss,
            "expected_origin_bps": self.expected_origin_bps,
            "expected_hit_ratio": self.expected_hit_ratio,
            "safe": self.safe,
            "warnings": list(self.warnings),
            "rejection_reasons": list(self.rejection_reasons),
            "live_pilot_claim": False,
            "label": "lab_capacity_plan",
        }


def plan_branch_cache_capacity(inp: CapacityPlanInput) -> CapacityPlan:
    """Deterministic capacity plan from ABR measurements. Rejects unsafe inputs."""
    warnings: list[str] = []
    rejections: list[str] = []

    if not inp.renditions:
        raise CapacityPlanError("at least one rendition required", code="empty_renditions")
    if len(inp.renditions) > MAX_RENDITIONS:
        raise CapacityPlanError("too many renditions", code="too_many_renditions")

    bitrates: list[int] = []
    for r in inp.renditions:
        label = (r.label or "").strip()
        if not label or len(label) > 32:
            raise CapacityPlanError("invalid rendition label", code="label")
        bitrates.append(_require_int("bitrate_bps", r.bitrate_bps, min_v=1, max_v=MAX_BITRATE_BPS))

    peak = _require_int(
        "peak_concurrent_viewers", inp.peak_concurrent_viewers, min_v=1, max_v=MAX_PEAK_VIEWERS
    )
    titles = _require_int(
        "working_set_titles", inp.working_set_titles, min_v=1, max_v=MAX_WORKING_SET_TITLES
    )
    duration_h = _require_float(
        "avg_title_duration_hours", inp.avg_title_duration_hours, min_v=0.05, max_v=12.0
    )
    retention_h = _require_float(
        "retention_hours", inp.retention_hours, min_v=1.0, max_v=float(MAX_RETENTION_HOURS)
    )
    repl = _require_int(
        "replication_factor", inp.replication_factor, min_v=1, max_v=MAX_REPLICATION
    )
    headroom = _require_int(
        "headroom_percent", inp.headroom_percent, min_v=0, max_v=MAX_HEADROOM_PCT
    )
    hit = _require_float("expected_hit_ratio", inp.expected_hit_ratio, min_v=0.0, max_v=0.99)
    high_r = _require_float("high_watermark_ratio", inp.high_watermark_ratio, min_v=0.5, max_v=0.98)
    low_r = _require_float("low_watermark_ratio", inp.low_watermark_ratio, min_v=0.2, max_v=0.95)
    min_free = _require_int("min_free_bytes", inp.min_free_bytes, min_v=0, max_v=MAX_BYTES)

    if low_r >= high_r:
        raise CapacityPlanError(
            "low_watermark_ratio must be < high_watermark_ratio", code="watermarks"
        )

    per_title = 0
    for bps in bitrates:
        chunk = bytes_for_bitrate_hour(bps, duration_h)
        if per_title > MAX_BYTES - chunk:
            raise CapacityPlanError("package size exceeds ceiling", code="overflow")
        per_title += chunk

    working = checked_mul(per_title, titles)
    # Retention multiplies working set by how many "title-hours" of churn we keep.
    # retention_factor = max(1, retention_hours / duration_hours) capped.
    retention_factor = max(1, int(retention_h / duration_h + 0.999999))
    if retention_factor > 10_000:
        raise CapacityPlanError("retention factor too large", code="bounds")
    retention_bytes = checked_mul(working, retention_factor)
    replicated = checked_mul(retention_bytes, repl)

    # Headroom: replicated * (1 + headroom/100)
    with_headroom = replicated + checked_mul(replicated, headroom) // 100
    if with_headroom > MAX_BYTES:
        rejections.append("recommended_disk_exceeds_ceiling")

    recommended = with_headroom + min_free
    if recommended > MAX_BYTES:
        rejections.append("recommended_disk_plus_min_free_exceeds_ceiling")

    high_wm = int(recommended * high_r)
    low_wm = int(recommended * low_r)
    if high_wm - low_wm < min_free and min_free > 0:
        warnings.append("watermark_gap_smaller_than_min_free")

    top_bitrate = max(bitrates)
    peak_origin_miss = checked_mul(top_bitrate, peak)  # worst case all miss at top ladder
    expected_origin = int(peak_origin_miss * (1.0 - hit))

    if inp.origin_egress_cap_bps is not None:
        cap = _require_int(
            "origin_egress_cap_bps",
            inp.origin_egress_cap_bps,
            min_v=1,
            max_v=checked_mul(MAX_BITRATE_BPS, MAX_PEAK_VIEWERS),
        )
        if expected_origin > cap:
            rejections.append("expected_origin_bps_exceeds_cap")
        if peak_origin_miss > cap * 4:
            warnings.append("cold_start_origin_spike_may_exceed_cap")

    if hit < 0.5:
        warnings.append("low_expected_hit_ratio")
    if repl > 2:
        warnings.append("high_replication_cost")

    safe = not rejections
    return CapacityPlan(
        package_bytes_per_title=per_title,
        working_set_bytes=working,
        retention_bytes=retention_bytes,
        replicated_bytes=replicated,
        with_headroom_bytes=with_headroom,
        recommended_disk_bytes=recommended if recommended <= MAX_BYTES else MAX_BYTES,
        high_watermark_bytes=high_wm,
        low_watermark_bytes=low_wm,
        min_free_bytes=min_free,
        peak_origin_bps_on_miss=peak_origin_miss,
        expected_origin_bps=expected_origin,
        expected_hit_ratio=hit,
        safe=safe,
        warnings=tuple(warnings),
        rejection_reasons=tuple(rejections),
    )
