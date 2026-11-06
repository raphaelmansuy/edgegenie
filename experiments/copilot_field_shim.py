#!/usr/bin/env python3
"""Strip Copilot-private fields before they reach the Databricks AI Gateway.

Why this exists
---------------
GitHub Copilot CLI (1.0.106) tags some chat messages with a private field,
`__copilotMessageSource`. The Databricks AI Gateway validates request bodies strictly and answers

    400 Bad request: json: unknown field "__copilotMessageSource"

so Copilot works for the first model call and dies on the next one, after its first tool call.
This tiny local proxy removes every key that starts with "__copilot" (at any depth) and forwards
the request unchanged otherwise. The caller's Authorization header is passed through.

Run:  UPSTREAM_BASE=https://<workspace>/ai-gateway/openai/v1 python3 copilot_field_shim.py
Then: COPILOT_PROVIDER_BASE_URL=http://127.0.0.1:8791/v1
"""
from __future__ import annotations

import http.server
import json
import os
import urllib.error
import urllib.request

UPSTREAM = os.environ["UPSTREAM_BASE"].rstrip("/")
PORT = int(os.environ.get("SHIM_PORT", "8791"))
PREFIX = "__copilot"


def clean(x):
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items() if not k.startswith(PREFIX)}
    if isinstance(x, list):
        return [clean(v) for v in x]
    return x


class Shim(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _forward(self, method: str):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else None
        if raw:
            try:
                raw = json.dumps(clean(json.loads(raw))).encode()
            except Exception:
                pass
        path = self.path[3:] if self.path.startswith("/v1") else self.path
        req = urllib.request.Request(
            UPSTREAM + path, data=raw, method=method,
            headers={"Authorization": self.headers.get("Authorization", ""),
                     "Content-Type": "application/json", "Accept": self.headers.get("Accept", "*/*")})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                status, body, ctype = r.status, r.read(), r.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as e:
            status, body, ctype = e.code, e.read(), "application/json"
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self._forward("POST")

    def do_GET(self):
        self._forward("GET")


if __name__ == "__main__":
    print(f"copilot field shim on :{PORT} -> {UPSTREAM}", flush=True)
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Shim).serve_forever()
