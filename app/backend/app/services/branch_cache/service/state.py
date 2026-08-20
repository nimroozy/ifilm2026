"""Runtime state for drain / graceful shutdown."""

from __future__ import annotations

import threading


class BranchServiceState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.draining = False
        self.shutting_down = False
        self.requests_in_flight = 0

    def begin_request(self) -> bool:
        with self._lock:
            if self.shutting_down:
                return False
            self.requests_in_flight += 1
            return True

    def end_request(self) -> None:
        with self._lock:
            self.requests_in_flight = max(0, self.requests_in_flight - 1)

    def start_drain(self) -> None:
        with self._lock:
            self.draining = True

    def start_shutdown(self) -> None:
        with self._lock:
            self.shutting_down = True
            self.draining = True

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "draining": self.draining,
                "shutting_down": self.shutting_down,
                "requests_in_flight": self.requests_in_flight,
            }
