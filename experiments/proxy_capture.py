#!/usr/bin/env python3
"""Logging proxy used to capture what a coding agent actually sends to the
Databricks AI Gateway. Writes each request body to /tmp/capture/NNN.json and
forwards the request unchanged.
"""
import http.server
import json
import os
import urllib.request

UPSTREAM = "https://dbc-cb61f1e1-bd8e.cloud.databricks.com/ai-gateway/openai/v1"
OUT = "/tmp/capture"
os.makedirs(OUT, exist_ok=True)
counter = {"n": 0}


class Proxy(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        counter["n"] += 1
        idx = counter["n"]
        with open(f"{OUT}/{idx:03d}.json", "wb") as fh:
            fh.write(body)
        forward_headers = {
            k: v
            for k, v in self.headers.items()
            if k.lower() in ("authorization", "content-type", "accept", "user-agent")
        }
        req = urllib.request.Request(
            UPSTREAM + self.path.replace("/v1", "", 1),
            data=body,
            headers=forward_headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                status = resp.status
                payload = resp.read()
                ctype = resp.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as exc:
            status = exc.code
            payload = exc.read()
            ctype = exc.headers.get("Content-Type", "application/json")
            with open(f"{OUT}/{idx:03d}.err", "wb") as fh:
                fh.write(payload)
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        body = json.dumps({"object": "list", "data": []}).encode()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(("127.0.0.1", 8787), Proxy).serve_forever()
