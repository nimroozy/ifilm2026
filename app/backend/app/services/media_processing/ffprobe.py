"""ffprobe JSON execution."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from app.core.config import Settings
from app.services.media_processing.errors import ProbeFailedError, ProbeParseError
from app.services.media_processing.ffmpeg import ProcessResult, resolve_binary, run_process


def build_ffprobe_argv(binary: str, media_path: Path) -> list[str]:
    return [
        binary,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(media_path),
    ]


def run_ffprobe(
    settings: Settings,
    media_path: Path,
    *,
    cancel_check: Callable[[], bool] | None = None,
) -> tuple[dict, ProcessResult]:
    binary = resolve_binary(settings.ffprobe_binary, label="ffprobe")
    argv = build_ffprobe_argv(binary, media_path)
    result = run_process(
        argv,
        timeout_seconds=float(settings.media_processing_probe_timeout_seconds),
        max_stdout_bytes=settings.media_processing_log_max_bytes,
        max_stderr_bytes=settings.media_processing_log_max_bytes,
        cancel_check=cancel_check,
    )
    if result.returncode != 0:
        err = result.stderr.decode("utf-8", errors="replace").strip() or "ffprobe failed"
        raise ProbeFailedError(err[:2000], code="probe_failed")
    try:
        payload = json.loads(result.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProbeParseError("Malformed ffprobe JSON") from exc
    if not isinstance(payload, dict):
        raise ProbeParseError("ffprobe JSON root must be an object")
    return payload, result
