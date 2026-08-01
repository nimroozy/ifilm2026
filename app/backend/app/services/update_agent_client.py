"""Unix-domain client for the privileged ifilm-update-agent.

The web application never runs root shell commands. All privileged update
operations go through this narrow typed protocol.
"""

from __future__ import annotations

import json
import socket
from typing import Any

from app.core.config import get_settings


class UpdateAgentError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


class UpdateAgentClient:
    def __init__(self, socket_path: str | None = None, shared_secret: str | None = None) -> None:
        settings = get_settings()
        self.socket_path = socket_path or settings.update_agent_socket
        self.shared_secret = shared_secret if shared_secret is not None else settings.update_agent_shared_secret

    def call(self, command: str, payload: dict[str, Any] | None = None, *, timeout: float = 120.0) -> dict[str, Any]:
        body = dict(payload or {})
        body["shared_secret"] = self.shared_secret
        request = {"command": command, "payload": body}
        raw = (json.dumps(request) + "\n").encode("utf-8")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            try:
                sock.connect(self.socket_path)
            except OSError as exc:
                raise UpdateAgentError("agent_unavailable", "update agent is not available") from exc
            sock.sendall(raw)
            chunks: list[bytes] = []
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
                if b"\n" in chunk:
                    break
        data = b"".join(chunks).decode("utf-8").strip()
        if not data:
            raise UpdateAgentError("empty_response", "update agent returned an empty response")
        try:
            resp = json.loads(data.splitlines()[0])
        except json.JSONDecodeError as exc:
            raise UpdateAgentError("invalid_response", "update agent returned invalid JSON") from exc
        if not resp.get("ok"):
            err = resp.get("error") or {}
            raise UpdateAgentError(str(err.get("code") or "agent_error"), str(err.get("message") or "agent error"))
        result = resp.get("result")
        if not isinstance(result, dict):
            raise UpdateAgentError("invalid_response", "update agent result must be an object")
        return result


def get_update_agent_client() -> UpdateAgentClient:
    return UpdateAgentClient()
