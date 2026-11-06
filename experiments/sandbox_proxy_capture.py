#!/usr/bin/env python3
"""Runs INSIDE the Databricks sandbox. Logs every request body a coding agent
sends, then forwards it to the Databricks AI Gateway.

Bodies land in /tmp/capture/NNN.json, error responses in /tmp/capture/NNN.err.
"""
import http.server
import json
import os
import urllib.error
import urllib.request

UPSTREAM = os.environ.get(
    "UPSTREAM", "https://dbc-cb61f1e1-bd8e.cloud.databricks.com/ai-gateway/openai/v1"
)
TOKEN = os.environ["DBX_TOKEN"]
OUT = "/tmp/capture"
os.makedirs(OUT, exist_ok=True)
n = {"i": 0}


class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _relay(self, method):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        if method == "POST":
            n["i"] += 1
            idx = n["i"]
            with open(f"{OUT}/{idx:03d}.json", "wb") as fh:
                fh.write(body)
        path = self.path.split("?")[0]
        url = UPSTREAM + (path[3:] if path.startswith("/v1") else path)
        headers = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
        req = urllib.request.Request(url, data=body or None, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=240) as r:
                status, payload, ctype = r.status, r.read(), r.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as e:
            status, payload, ctype = e.code, e.read(), e.headers.get("Content-Type", "application/json")
            if method == "POST":
                with open(f"{OUT}/{idx:03d}.err", "wb") as fh:
                    fh.write(payload)
        except Exception as e:  # noqa: BLE001
            payload = json.dumps({"error": str(e)}).encode()
            status, ctype = 502, "application/json"
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        self._relay("POST")

    def do_GET(self):
        self._relay("GET")


http.server.ThreadingHTTPServer(("127.0.0.1", 8787), H).serve_forever()
