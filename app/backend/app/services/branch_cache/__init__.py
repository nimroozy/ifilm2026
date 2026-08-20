"""Hybrid CDN branch-cache package.

Submodules are imported explicitly by callers. This package ``__init__``
intentionally avoids eager imports of the control-plane registry (SQLAlchemy
models) so the Phase 6/7 isolated HTTP service artifact can start without a
database driver or customer-store connection.
"""

from __future__ import annotations

__all__ = [
    "grants",
    "metrics",
    "registry",
    "routing",
    "validation",
]


def __getattr__(name: str):
    """Lazy submodule access for ``from app.services.branch_cache import X``."""
    if name in __all__:
        import importlib

        return importlib.import_module(f"app.services.branch_cache.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
