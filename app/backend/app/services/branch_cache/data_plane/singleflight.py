"""Single-flight / request coalescing for concurrent cache fills."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any, TypeVar

T = TypeVar("T")


class SingleFlight:
    """Ensure only one in-flight callable runs per key; waiters share the result."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._inflight: dict[str, threading.Event] = {}
        self._results: dict[str, tuple[Any, BaseException | None]] = {}

    def do(self, key: str, fn: Callable[[], T]) -> tuple[T, bool]:
        """Return (result, coalesced). coalesced=True if this caller waited."""
        with self._lock:
            existing = self._inflight.get(key)
            if existing is not None:
                event = existing
                waiter = True
            else:
                event = threading.Event()
                self._inflight[key] = event
                waiter = False

        if waiter:
            event.wait(timeout=120)
            with self._lock:
                stored = self._results.get(key)
            if stored is None:
                raise RuntimeError("missing single-flight result")
            waited_result, waited_exc = stored
            if waited_exc is not None:
                raise waited_exc
            return waited_result, True

        run_exc: BaseException | None = None
        run_result: Any = None
        try:
            run_result = fn()
        except BaseException as err:  # noqa: BLE001
            run_exc = err
        with self._lock:
            self._results[key] = (run_result, run_exc)
            done = self._inflight.pop(key, None)
            if done is not None:
                done.set()
            if len(self._results) > 1024:
                keep = self._results.pop(key, None)
                self._results.clear()
                if keep is not None:
                    self._results[key] = keep
        if run_exc is not None:
            raise run_exc
        return run_result, False
