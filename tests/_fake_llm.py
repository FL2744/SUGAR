"""A tiny in-process OpenAI-compatible server used to exercise the real HTTP provider code."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable


class FakeLLMServer:
    def __init__(self, *, api_key: str = "sk-test-valid-key-1234567890", models: list[str] | None = None,
                 reply: str | Callable[[dict[str, Any]], str] = "ok", supports_schema: bool = True,
                 token_param: str = "max_completion_tokens", require_auth: bool = True) -> None:
        self.api_key = api_key
        self.models = models if models is not None else ["gpt-test", "gpt-other"]
        self.reply = reply
        self.supports_schema = supports_schema
        self.token_param = token_param
        self.require_auth = require_auth
        self.requests: list[dict[str, Any]] = []
        self.status_queue: list[tuple[int, dict[str, Any]]] = []   # forced responses, consumed in order
        self.list_status = 200
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:  # silence
                pass

            def _send(self, status: int, payload: dict[str, Any]) -> None:
                body = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _authorized(self) -> bool:
                if not outer.require_auth:
                    return True
                return self.headers.get("Authorization", "") == f"Bearer {outer.api_key}"

            def do_GET(self) -> None:
                outer.requests.append({"method": "GET", "path": self.path, "headers": dict(self.headers)})
                if not self._authorized():
                    self._send(401, {"error": {"message": "Incorrect API key provided", "code": "invalid_api_key"}})
                    return
                if outer.list_status != 200:
                    self._send(outer.list_status, {"error": {"message": "not found"}})
                    return
                self._send(200, {"data": [{"id": m} for m in outer.models]})

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length) or b"{}")
                outer.requests.append({"method": "POST", "path": self.path, "headers": dict(self.headers), "body": body})
                if outer.status_queue:
                    status, payload = outer.status_queue.pop(0)
                    self._send(status, payload)
                    return
                if not self._authorized():
                    self._send(401, {"error": {"message": "Incorrect API key provided", "code": "invalid_api_key"}})
                    return
                if body.get("model") not in outer.models:
                    self._send(404, {"error": {"message": f"The model `{body.get('model')}` does not exist", "code": "model_not_found"}})
                    return
                if "max_tokens" in body and outer.token_param == "max_completion_tokens":
                    self._send(400, {"error": {"message": "Unsupported parameter: 'max_tokens' is not supported with this model. Use 'max_completion_tokens' instead.",
                                               "param": "max_tokens", "code": "unsupported_parameter"}})
                    return
                if "max_completion_tokens" in body and outer.token_param == "max_tokens":
                    self._send(400, {"error": {"message": "Unsupported parameter: max_completion_tokens", "param": "max_completion_tokens",
                                               "code": "unsupported_parameter"}})
                    return
                response_format = body.get("response_format")
                if response_format and response_format.get("type") == "json_schema" and not outer.supports_schema:
                    self._send(400, {"error": {"message": "response_format json_schema is not supported", "param": "response_format"}})
                    return
                text = outer.reply(body) if callable(outer.reply) else outer.reply
                self._send(200, {"model": body.get("model"), "choices": [{"message": {"role": "assistant", "content": text}}],
                                 "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8}})

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}/v1"

    def __enter__(self) -> "FakeLLMServer":
        self._thread.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)
