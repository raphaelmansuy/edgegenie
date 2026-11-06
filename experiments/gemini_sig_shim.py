#!/usr/bin/env python3
"""Thought-signature preserving shim: OpenAI-compatible in, Vertex AI out.

Why this exists
---------------
Gemini 3.x reasoning models return an opaque `thought_signature` on every
function-call part and *require* it to be echoed back on the next turn. The
signature is carried in the non-standard `extra_content.google.thought_signature`
field. OpenAI-compatible clients (OpenCode, most agent frameworks) serialise
tool calls into their own message model and drop unknown fields, so the second
turn fails with:

    Function call is missing a thought_signature in functionCall parts.

This shim sits between the agent and Vertex AI, remembers signatures by
tool_call id, and re-attaches them on the way back in.

Run:  VX_TOKEN=$(gcloud auth print-access-token) python3 gemini_sig_shim.py
"""
from __future__ import annotations

import http.server
import json
import os
import urllib.error
import urllib.request

PROJECT = os.environ.get("VX_PROJECT", "mobioos-506015")
LOCATION = os.environ.get("VX_LOCATION", "global")
TOKEN = os.environ["VX_TOKEN"]
UPSTREAM = (
    f"https://aiplatform.googleapis.com/v1/projects/{PROJECT}"
    f"/locations/{LOCATION}/endpoints/openapi/chat/completions"
)
PORT = int(os.environ.get("SHIM_PORT", "8790"))

# tool_call_id -> extra_content blob returned by Gemini
SIGNATURES: dict[str, dict] = {}


def remember(body: bytes) -> None:
    """Store signatures from an assistant response before it loses them."""
    try:
        data = json.loads(body)
    except Exception:
        return
    choices = data.get("choices") or []
    if not choices:
        return
    for call in choices[0].get("message", {}).get("tool_calls") or []:
        extra = call.get("extra_content")
        if extra and call.get("id"):
            SIGNATURES[call["id"]] = extra


def restore(payload: dict) -> dict:
    """Re-attach remembered signatures to outgoing assistant tool calls."""
    for msg in payload.get("messages", []):
        for call in msg.get("tool_calls") or []:
            cid = call.get("id")
            if cid in SIGNATURES and not call.get("extra_content"):
                call["extra_content"] = SIGNATURES[cid]
    return payload


class Shim(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        payload = restore(json.loads(raw or b"{}"))
        req = urllib.request.Request(
            UPSTREAM,
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=240) as r:
                status, body = r.status, r.read()
                ctype = r.headers.get("Content-Type", "application/json")
        except urllib.error.HTTPError as e:
            status, body, ctype = e.code, e.read(), "application/json"
        if status == 200 and not payload.get("stream"):
            remember(body)
        elif status == 200 and payload.get("stream"):
            remember_stream(body)
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        body = json.dumps(
            {"object": "list", "data": [{"id": "google/gemini-3.8-flash", "object": "model"}]}
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def remember_stream(body: bytes) -> None:
    """Reassemble streamed tool calls and capture their signatures."""
    acc: dict[int, dict] = {}
    for line in body.decode("utf-8", "replace").splitlines():
        if not line.startswith("data: "):
            continue
        chunk = line[6:].strip()
        if chunk == "[DONE]":
            continue
        try:
            data = json.loads(chunk)
        except Exception:
            continue
        for choice in data.get("choices") or []:
            for call in choice.get("delta", {}).get("tool_calls") or []:
                idx = call.get("index", 0)
                slot = acc.setdefault(idx, {})
                if call.get("id"):
                    slot["id"] = call["id"]
                if call.get("extra_content"):
                    slot["extra_content"] = call["extra_content"]
    for slot in acc.values():
        if slot.get("id") and slot.get("extra_content"):
            SIGNATURES[slot["id"]] = slot["extra_content"]


if __name__ == "__main__":
    print(f"shim on :{PORT} -> {UPSTREAM}", flush=True)
    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Shim).serve_forever()
