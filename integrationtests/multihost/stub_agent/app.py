"""Stub boardfarm agent for multi-host integration tests (standard library only)."""

from __future__ import annotations

import io
import json
import os
import tarfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

_STATE: dict[str, object] = {"state": "idle", "booted": False}


def _bundle() -> bytes:
    buffer = io.BytesIO()
    payload = f"stub agent {os.environ.get('BOARDFARM_SESSION_ID')}\n".encode()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        info = tarfile.TarInfo("stub.log")
        info.size = len(payload)
        archive.addfile(info, io.BytesIO(payload))
    return buffer.getvalue()


class _Handler(BaseHTTPRequestHandler):
    """Answers the agent routes the control plane calls."""

    def _send(
        self, status: int, body: object, content_type: str = "application/json"
    ) -> None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _drain(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)

    def do_GET(self) -> None:
        """Serve health, session state, echo and the diagnostics bundle."""
        if self.path == "/health":
            self._send(200, {"status": "ok"})
        elif self.path == "/session":
            self._send(200, {**_STATE, "last_activity": time.time(), "liveness": None})
        elif self.path == "/echo":
            self._send(
                200,
                {
                    "session": os.environ.get("BOARDFARM_SESSION_ID"),
                    "board": os.environ.get("BOARDFARM_BOARD_NAME"),
                },
            )
        elif self.path == "/diagnostics/bundle":
            self._send(200, _bundle(), "application/gzip")
        else:
            self._send(404, {"detail": "not found"})

    def do_POST(self) -> None:
        """Accept config and boot."""
        self._drain()
        if self.path == "/session/config":
            _STATE["state"] = "configured"
            self._send(200, _STATE)
        elif self.path.startswith("/session/boot"):
            _STATE["state"] = "ready"
            self._send(202, {"boot_job_id": "j-stub", "state": "ready"})
        else:
            self._send(404, {"detail": "not found"})

    def do_DELETE(self) -> None:
        """Release the session."""
        if self.path == "/session":
            _STATE["state"] = "released"
            self._send(200, _STATE)
        else:
            self._send(404, {"detail": "not found"})

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Stay quiet."""


if __name__ == "__main__":
    port = int(os.environ.get("BOARDFARM_AGENT_PORT", "8000"))
    ThreadingHTTPServer(("0.0.0.0", port), _Handler).serve_forever()  # noqa: S104
