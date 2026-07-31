"""Safe subprocess helpers for FFmpeg tooling (no shell)."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from shutil import which

from app.services.media_processing.errors import (
    BinaryNotFoundError,
    EncodeCancelledError,
    EncodeTimeoutError,
    ProbeCancelledError,
    ProbeFailedError,
    ProbeTimeoutError,
)


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: bytes
    stderr: bytes
    truncated_stdout: bool
    truncated_stderr: bool
    timed_out: bool


def resolve_binary(configured: str, *, label: str) -> str:
    """Resolve an executable path; raise if missing."""
    candidate = (configured or "").strip() or label
    path = which(candidate)
    if path is not None:
        return path
    p = Path(candidate)
    if p.is_file() and os.access(p, os.X_OK):
        return str(p.resolve())
    raise BinaryNotFoundError(f"{label} binary not found: {candidate}")


def binary_available(configured: str) -> bool:
    try:
        resolve_binary(configured, label=configured or "binary")
        return True
    except BinaryNotFoundError:
        return False


def _kill_process_group(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            pass


def run_process(
    argv: list[str],
    *,
    timeout_seconds: float,
    max_stdout_bytes: int,
    max_stderr_bytes: int,
    cancel_check: Callable[[], bool] | None = None,
    poll_interval: float = 0.2,
    cancel_error: type[Exception] = ProbeCancelledError,
    timeout_error: type[Exception] = ProbeTimeoutError,
) -> ProcessResult:
    """Run argv as a process group with bounded output capture and cancellation."""
    if not argv:
        raise ProbeFailedError("Empty process argv")

    proc = subprocess.Popen(  # noqa: S603 — argv list, never shell
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        shell=False,
    )

    stdout_chunks: list[bytes] = []
    stderr_chunks: list[bytes] = []
    stdout_size = 0
    stderr_size = 0
    truncated_stdout = False
    truncated_stderr = False
    lock = threading.Lock()

    def _reader(stream, chunks: list[bytes], is_stdout: bool) -> None:
        nonlocal stdout_size, stderr_size, truncated_stdout, truncated_stderr
        assert stream is not None
        while True:
            data = stream.read(8192)
            if not data:
                break
            with lock:
                if is_stdout:
                    remaining = max_stdout_bytes - stdout_size
                    if remaining <= 0:
                        truncated_stdout = True
                        continue
                    chunk = data[:remaining]
                    chunks.append(chunk)
                    stdout_size += len(chunk)
                    if len(data) > remaining:
                        truncated_stdout = True
                else:
                    remaining = max_stderr_bytes - stderr_size
                    if remaining <= 0:
                        truncated_stderr = True
                        continue
                    chunk = data[:remaining]
                    chunks.append(chunk)
                    stderr_size += len(chunk)
                    if len(data) > remaining:
                        truncated_stderr = True

    t_out = threading.Thread(target=_reader, args=(proc.stdout, stdout_chunks, True), daemon=True)
    t_err = threading.Thread(target=_reader, args=(proc.stderr, stderr_chunks, False), daemon=True)
    t_out.start()
    t_err.start()

    deadline = time.monotonic() + timeout_seconds
    timed_out = False
    cancelled = False
    try:
        while True:
            if cancel_check is not None and cancel_check():
                cancelled = True
                _kill_process_group(proc)
                break
            if time.monotonic() >= deadline:
                timed_out = True
                _kill_process_group(proc)
                break
            if proc.poll() is not None:
                break
            time.sleep(poll_interval)
        t_out.join(timeout=2)
        t_err.join(timeout=2)
        if proc.poll() is None:
            _kill_process_group(proc)
    finally:
        if proc.stdout:
            proc.stdout.close()
        if proc.stderr:
            proc.stderr.close()

    with lock:
        stdout = b"".join(stdout_chunks)
        stderr = b"".join(stderr_chunks)

    if cancelled:
        raise cancel_error("Process cancelled")
    if timed_out:
        raise timeout_error(f"Process timed out after {timeout_seconds}s")

    return ProcessResult(
        returncode=int(proc.returncode if proc.returncode is not None else -1),
        stdout=stdout,
        stderr=stderr,
        truncated_stdout=truncated_stdout,
        truncated_stderr=truncated_stderr,
        timed_out=False,
    )


def parse_progress_line(line: str, state: dict[str, str]) -> dict[str, str] | None:
    """Accumulate ffmpeg -progress key=value lines; return snapshot on progress=."""
    text = line.strip()
    if not text or "=" not in text:
        return None
    key, _, value = text.partition("=")
    key = key.strip()
    value = value.strip()
    if not key:
        return None
    state[key] = value
    if key == "progress":
        return dict(state)
    return None


def run_process_with_progress(
    argv: list[str],
    *,
    timeout_seconds: float,
    max_stderr_bytes: int,
    cancel_check: Callable[[], bool] | None = None,
    on_progress: Callable[[dict[str, str]], None] | None = None,
    poll_interval: float = 0.2,
) -> ProcessResult:
    """Run argv, parse ffmpeg -progress pipe:1 stdout, bound stderr only."""
    if not argv:
        raise ProbeFailedError("Empty process argv")

    proc = subprocess.Popen(  # noqa: S603 — argv list, never shell
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
        shell=False,
        text=False,
    )

    stderr_chunks: list[bytes] = []
    stderr_size = 0
    truncated_stderr = False
    progress_state: dict[str, str] = {}
    lock = threading.Lock()
    stdout_buf = bytearray()

    def _stderr_reader() -> None:
        nonlocal stderr_size, truncated_stderr
        assert proc.stderr is not None
        while True:
            data = proc.stderr.read(8192)
            if not data:
                break
            with lock:
                remaining = max_stderr_bytes - stderr_size
                if remaining <= 0:
                    truncated_stderr = True
                    continue
                chunk = data[:remaining]
                stderr_chunks.append(chunk)
                stderr_size += len(chunk)
                if len(data) > remaining:
                    truncated_stderr = True

    def _stdout_reader() -> None:
        assert proc.stdout is not None
        while True:
            data = proc.stdout.read(1024)
            if not data:
                break
            with lock:
                stdout_buf.extend(data)
                while True:
                    nl = stdout_buf.find(b"\n")
                    if nl < 0:
                        break
                    raw_line = bytes(stdout_buf[:nl])
                    del stdout_buf[: nl + 1]
                    line = raw_line.decode("utf-8", errors="replace")
                    snapshot = parse_progress_line(line, progress_state)
                    if snapshot is not None and on_progress is not None:
                        on_progress(snapshot)

    t_out = threading.Thread(target=_stdout_reader, daemon=True)
    t_err = threading.Thread(target=_stderr_reader, daemon=True)
    t_out.start()
    t_err.start()

    deadline = time.monotonic() + timeout_seconds
    timed_out = False
    cancelled = False
    try:
        while True:
            if cancel_check is not None and cancel_check():
                cancelled = True
                _kill_process_group(proc)
                break
            if time.monotonic() >= deadline:
                timed_out = True
                _kill_process_group(proc)
                break
            if proc.poll() is not None:
                break
            time.sleep(poll_interval)
        t_out.join(timeout=2)
        t_err.join(timeout=2)
        if proc.poll() is None:
            _kill_process_group(proc)
    finally:
        if proc.stdout:
            proc.stdout.close()
        if proc.stderr:
            proc.stderr.close()

    with lock:
        stderr = b"".join(stderr_chunks)

    if cancelled:
        raise EncodeCancelledError("Encode cancelled")
    if timed_out:
        raise EncodeTimeoutError(f"Encode timed out after {timeout_seconds}s")

    return ProcessResult(
        returncode=int(proc.returncode if proc.returncode is not None else -1),
        stdout=b"",
        stderr=stderr,
        truncated_stdout=False,
        truncated_stderr=truncated_stderr,
        timed_out=False,
    )
