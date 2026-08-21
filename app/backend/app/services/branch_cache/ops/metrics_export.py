"""Bounded-cardinality metrics export for future Prometheus integration.

No HTTP endpoint is enabled in Phase 5. Labels are restricted to a fixed allowlist.
"""

from __future__ import annotations

import re
from typing import Any

from app.services.branch_cache import metrics
from app.services.branch_cache.grants import redact_secrets_from_mapping

# Fixed metric names only — never accept dynamic label keys from callers.
_ALLOWED_METRICS = frozenset(
    {
        "nodes_created",
        "heartbeats_recorded",
        "routing_decisions",
        "routing_branch_selected",
        "routing_central_fallback",
        "edge_grants_issued",
        "edge_grants_verified_ok",
        "edge_grants_verified_fail",
        "dp_hit",
        "dp_miss",
        "dp_fill_ok",
        "dp_fill_fail",
        "dp_coalesced",
        "dp_evicted",
        "dp_fallback",
        "dp_auth_fail",
        "dp_bytes_origin",
        "dp_bytes_served",
        "dp_prewarm_ok",
        "dp_prewarm_fail",
    }
)

_FORBIDDEN_LABEL_KEYS = frozenset(
    {
        "token",
        "session",
        "session_id",
        "subscriber",
        "subscriber_id",
        "ip",
        "client_ip",
        "url",
        "raw_url",
        "object_key",
        "path",
        "credential",
        "secret",
        "password",
        "authorization",
        "grant",
        "private_key",
    }
)

_SAFE_LABEL_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_SAFE_LABEL_VAL_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class MetricsExportError(ValueError):
    def __init__(self, message: str, *, code: str = "invalid_metrics") -> None:
        super().__init__(message)
        self.code = code


def _validate_labels(labels: dict[str, str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    if not labels:
        return out
    if len(labels) > 4:
        raise MetricsExportError("too many labels", code="cardinality")
    for k, v in labels.items():
        lk = str(k).lower()
        if lk in _FORBIDDEN_LABEL_KEYS or any(f in lk for f in _FORBIDDEN_LABEL_KEYS):
            raise MetricsExportError(f"forbidden label key: {k}", code="forbidden_label")
        if not _SAFE_LABEL_RE.match(k):
            raise MetricsExportError(f"unsafe label key: {k}", code="unsafe_label")
        if not _SAFE_LABEL_VAL_RE.match(str(v)):
            raise MetricsExportError(f"unsafe label value for {k}", code="unsafe_label_value")
        out[k] = str(v)
    return out


def snapshot_for_export(
    *,
    const_labels: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Return a redacted, bounded metrics snapshot suitable for future scrape adapters."""
    labels = _validate_labels(const_labels)
    # Only allow very low-cardinality const labels (e.g. node_role=branch_lab).
    for k in labels:
        if k not in {"node_role", "site_id", "env"}:
            raise MetricsExportError(f"label not allowlisted: {k}", code="label_not_allowed")
    raw = metrics.snapshot()
    filtered = {k: int(v) for k, v in raw.items() if k in _ALLOWED_METRICS}
    return redact_secrets_from_mapping(
        {
            "metrics": filtered,
            "labels": labels,
            "endpoint_enabled": False,
            "cardinality_policy": "fixed_names_only",
        }
    )


def render_prometheus_text(snapshot: dict[str, Any] | None = None) -> str:
    """Render Prometheus exposition text (lab helper only — no HTTP mount)."""
    data = snapshot or snapshot_for_export()
    labels = data.get("labels") or {}
    label_str = ""
    if labels:
        parts = [f'{k}="{v}"' for k, v in sorted(labels.items())]
        label_str = "{" + ",".join(parts) + "}"
    lines: list[str] = [
        "# HELP ifilm_branch_cache_info Branch cache lab metrics (endpoint disabled).",
        "# TYPE ifilm_branch_cache_info gauge",
        'ifilm_branch_cache_info{endpoint_enabled="false"} 1',
    ]
    for name, value in sorted((data.get("metrics") or {}).items()):
        if name not in _ALLOWED_METRICS:
            continue
        metric = f"ifilm_branch_cache_{name}"
        lines.append(f"# TYPE {metric} counter")
        lines.append(f"{metric}{label_str} {int(value)}")
    lines.append("")
    text = "\n".join(lines)
    # Redaction guard
    lowered = text.lower()
    for bad in ("private key", "bearer ", "password", "sas", "portal_secret"):
        if bad in lowered:
            raise MetricsExportError("secret leakage in metrics text", code="leak")
    return text
