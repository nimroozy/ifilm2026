"""HTTP Range header parsing for HLS segment delivery."""

from __future__ import annotations

from dataclasses import dataclass


class RangeError(Exception):
    def __init__(self, code: str = "invalid_range"):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ByteRange:
    start: int
    end: int  # inclusive

    @property
    def length(self) -> int:
        return self.end - self.start + 1


def parse_byte_range(header: str | None, *, file_size: int) -> ByteRange | None:
    """Parse a single byte range. Returns None if header absent.

    Raises RangeError for malformed or unsatisfiable ranges (→ 416).
    """
    if header is None or header.strip() == "":
        return None
    value = header.strip()
    if not value.lower().startswith("bytes="):
        raise RangeError("invalid_range")
    spec = value[6:].strip()
    if "," in spec:
        # Multiple ranges not supported in Phase 7.
        raise RangeError("invalid_range")
    if "-" not in spec:
        raise RangeError("invalid_range")
    start_s, end_s = spec.split("-", 1)
    if file_size <= 0:
        raise RangeError("unsatisfiable")

    if start_s == "" and end_s == "":
        raise RangeError("invalid_range")

    if start_s == "":
        # suffix bytes: last N bytes
        try:
            suffix = int(end_s)
        except ValueError as exc:
            raise RangeError("invalid_range") from exc
        if suffix <= 0:
            raise RangeError("invalid_range")
        if suffix >= file_size:
            return ByteRange(0, file_size - 1)
        return ByteRange(file_size - suffix, file_size - 1)

    try:
        start = int(start_s)
    except ValueError as exc:
        raise RangeError("invalid_range") from exc
    if start < 0 or start >= file_size:
        raise RangeError("unsatisfiable")

    if end_s == "":
        return ByteRange(start, file_size - 1)

    try:
        end = int(end_s)
    except ValueError as exc:
        raise RangeError("invalid_range") from exc
    if end < start:
        raise RangeError("invalid_range")
    end = min(end, file_size - 1)
    return ByteRange(start, end)
