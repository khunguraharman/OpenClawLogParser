from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
from typing import Callable


@dataclass
class HealthSnapshot:
    consumer_name: str
    active_log_path: str | None = None
    byte_offset: int = 0
    processed_lines: int = 0
    last_poll_at: datetime | None = None
    last_ingested_at: datetime | None = None
    last_error: str | None = None
    dry_run: bool = False

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["generated_at"] = datetime.now(timezone.utc).isoformat()
        for key in ("last_poll_at", "last_ingested_at"):
            value = payload[key]
            if isinstance(value, datetime):
                payload[key] = value.isoformat()
        return payload


class HealthServer:
    def __init__(self, host: str, port: int, snapshot_factory: Callable[[], HealthSnapshot]) -> None:
        self._server = ThreadingHTTPServer((host, port), self._make_handler(snapshot_factory))
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)

    def _make_handler(
        self,
        snapshot_factory: Callable[[], HealthSnapshot],
    ) -> type[BaseHTTPRequestHandler]:
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                if self.path not in {"/", "/health", "/healthz"}:
                    self.send_response(404)
                    self.end_headers()
                    return

                snapshot = snapshot_factory().to_dict()
                body = json.dumps(snapshot, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
                status_code = 503 if snapshot.get("last_error") else 200

                self.send_response(status_code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: object) -> None:
                return

        return Handler
