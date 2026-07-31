"""Media processing exceptions and progress constants."""

from __future__ import annotations


class MediaProcessingError(Exception):
    """Base processing error."""

    code = "processing_error"
    transient = False

    def __init__(self, message: str, *, code: str | None = None, transient: bool | None = None):
        super().__init__(message)
        if code is not None:
            self.code = code
        if transient is not None:
            self.transient = transient


class PermanentProcessingError(MediaProcessingError):
    transient = False


class TransientProcessingError(MediaProcessingError):
    transient = True


class BinaryNotFoundError(PermanentProcessingError):
    code = "binary_not_found"


class PathSecurityError(PermanentProcessingError):
    code = "path_security"


class AssetNotReadyError(PermanentProcessingError):
    code = "asset_not_ready"


class ProbeTimeoutError(TransientProcessingError):
    code = "probe_timeout"


class ProbeCancelledError(PermanentProcessingError):
    code = "cancelled"


class ProbeFailedError(PermanentProcessingError):
    code = "probe_failed"


class ProbeParseError(PermanentProcessingError):
    code = "probe_parse"


class UnsupportedMediaError(PermanentProcessingError):
    code = "unsupported_media"


class EncodeFailedError(PermanentProcessingError):
    code = "encode_failed"


class EncodeTimeoutError(TransientProcessingError):
    code = "encode_timeout"


class EncodeCancelledError(PermanentProcessingError):
    code = "cancelled"


class PackageValidationError(PermanentProcessingError):
    code = "package_validation"


class ProbeRequiredError(PermanentProcessingError):
    code = "probe_required"


PROGRESS_QUEUED = 0
PROGRESS_CLAIMED = 10
PROGRESS_VALIDATING = 30
PROGRESS_RUNNING_FFPROBE = 50
PROGRESS_PARSING = 75
PROGRESS_SAVING = 90
PROGRESS_ENCODING = 40
PROGRESS_WRITING_PLAYLISTS = 85
PROGRESS_VALIDATING_PACKAGE = 90
PROGRESS_PROMOTING = 95
PROGRESS_COMPLETED = 100

DIAGNOSTIC_MAX_CHARS = 2000
