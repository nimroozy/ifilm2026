"""Safe error codes for the branch data-plane simulation."""

from __future__ import annotations


class DataPlaneError(Exception):
    """Operational error with a stable, secret-free code."""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


# Stable reason / decision codes (low cardinality).
DECISION_HIT = "cache_hit"
DECISION_MISS_FILL = "cache_miss_filled"
DECISION_FALLBACK_CENTRAL = "central_origin_fallback"
DECISION_AUTH_DENIED = "auth_denied"
DECISION_DISABLED = "data_plane_disabled"
DECISION_DRAINING = "draining"
DECISION_BAD_RANGE = "bad_range"

CODE_AUTH = "auth_failed"
CODE_PATH = "path_rejected"
CODE_TRAVERSAL = "traversal_rejected"
CODE_SYMLINK = "symlink_rejected"
CODE_OUTSIDE_ROOT = "outside_cache_root"
CODE_ORIGIN = "origin_unavailable"
CODE_CHECKSUM = "checksum_mismatch"
CODE_SIZE = "size_mismatch"
CODE_TIMEOUT = "origin_timeout"
CODE_OVERSIZE = "object_too_large"
CODE_CANCELLED = "cancelled"
CODE_RANGE = "invalid_range"
CODE_DISABLED = "disabled"
CODE_POISON = "poison_rejected"
