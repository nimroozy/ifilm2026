"""Low-cardinality observability counters for branch-cache control plane."""

from __future__ import annotations

import threading
from typing import Any

_LOCK = threading.Lock()
_COUNTERS: dict[str, int] = {
    "nodes_created": 0,
    "heartbeats_recorded": 0,
    "routing_decisions": 0,
    "routing_branch_selected": 0,
    "routing_central_fallback": 0,
    "edge_grants_issued": 0,
    "edge_grants_verified_ok": 0,
    "edge_grants_verified_fail": 0,
}


def incr(name: str, amount: int = 1) -> None:
    with _LOCK:
        if name not in _COUNTERS:
            return  # ignore unknown / high-cardinality keys
        _COUNTERS[name] = int(_COUNTERS[name]) + int(amount)


def snapshot() -> dict[str, Any]:
    with _LOCK:
        return dict(_COUNTERS)


def reset_for_tests() -> None:
    with _LOCK:
        for k in _COUNTERS:
            _COUNTERS[k] = 0
