"""Production CDN node runtime (CDN-P1).

Runs only on provisioned CDN servers with ``ENABLE_CDN_NODE_SERVICE=true``.
Reuses the branch-cache data plane (grant verification, confined cache store,
single-flight pull-through fills, eviction) with a central HTTP origin fetcher
and a heartbeat client. Never loads central secrets or private signing keys.
"""

from app.services.cdn_node.config import (
    NodeRuntimeConfig,
    NodeRuntimeError,
    load_node_runtime_config,
)

__all__ = ["NodeRuntimeConfig", "NodeRuntimeError", "load_node_runtime_config"]
