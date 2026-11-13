"""Drive the product HTTP path; the grader never bypasses its permission boundary."""

from __future__ import annotations

import json
import os
import time
import urllib.request
from uuid import uuid4

TERMINAL = {
    "completed",
    "blocked",
    "failed",
    "cancelled",
    "interrupted",
    "declined",
    "refused",
    "truncated",
}


class AppDriver:
    def __init__(
        self, url: str, *, request=None, clock=time.monotonic, sleep=time.sleep
    ):
        self.url = url.rstrip("/")
        self.request = request or self._request
        self.clock, self.sleep = clock, sleep

    def _request(self, method: str, path: str, body=None):
        headers = {"Content-Type": "application/json"}
        token = os.environ.get("EXAM_APP_BEARER", "")
        if token:
            headers["Authorization"] = "Bearer " + token
        if body and "requestKey" in body:
            body = dict(body)
            headers["Idempotency-Key"] = body.pop("requestKey")
        req = urllib.request.Request(
            self.url + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers,
            method=method,
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.load(response)

    def verify(self, host: str, user: str) -> dict:
        identity = self.request("GET", "/api/me")
        connected = (identity.get("workspace") or {}).get("host", "").rstrip("/")
        # Databricks Apps' owner key is opaque. Compare the trusted proxy principal, not that key.
        principal = identity.get("username", identity.get("user"))
        if identity.get("demo") or connected != host.rstrip("/") or principal != user:
            raise RuntimeError(
                "The app identity/workspace does not match the grader. No mission was seeded."
            )
        return identity

    def prepare(
        self, *, folder: str, schema: str, model: str, autonomy: str = "review"
    ):
        if autonomy not in ("plan", "review", "auto"):
            raise ValueError("Invalid exam autonomy mode")
        session = self.request(
            "POST",
            "/api/sessions",
            {"folder": folder, "schema": schema, "model": model},
        )
        # Remembered product preferences must never silently change the benchmark's chosen mode.
        self.request("POST", f"/api/sessions/{session['id']}/mode", {"mode": autonomy})
        return session

    def run(
        self,
        *,
        folder: str,
        schema: str,
        model: str,
        prompt: str,
        timeout: float,
        autonomy: str = "review",
        prepared_session: dict | None = None,
    ) -> dict:
        session = prepared_session or self.prepare(
            folder=folder, schema=schema, model=model, autonomy=autonomy
        )
        sid = session["id"]
        receipt = self.request(
            "POST",
            f"/api/sessions/{sid}/messages",
            {"text": prompt, "requestKey": uuid4().hex},
        )
        tid = receipt["turnId"]
        deadline = self.clock() + timeout
        after, events = 0, []

        def drain():
            nonlocal after
            while True:
                page = self.request(
                    "GET", f"/api/sessions/{sid}/events?after={after}&limit=2000"
                )
                events.extend(page["events"])
                after = page["nextAfter"]
                if not page.get("hasMore"):
                    return

        while self.clock() < deadline:
            drain()
            status = self.request("GET", f"/api/sessions/{sid}")
            turns = status["turns"]
            current = turns[-1]
            # Later turns can be server-created verification or native-operation continuations.
            if current["status"] in TERMINAL:
                drain()  # Terminal state and the preceding text may have committed after the first read.
                answer = "\n".join(
                    "".join(
                        e.get("text", "")
                        for e in events
                        if e.get("turnId") == turn["id"]
                        and e["type"] == "message.delta"
                    )
                    for turn in turns
                )
                tools = {}
                for event in events:
                    if not event["type"].startswith("tool_call."):
                        continue
                    tools.setdefault(event["callId"], {}).update(event)
                return {
                    "via": "app",
                    "autonomy": autonomy,
                    "session_id": sid,
                    "turn_id": tid,
                    "status": current["status"],
                    "invalidReason": "The app runtime/credential interrupted before model execution"
                    if current["status"] == "interrupted" and not tools and not any(turn.get("usage", {}).get("input", 0) for turn in turns)
                    else "",
                    "events": events,
                    "answer": answer,
                    "all_text": answer,
                    "tools": list(tools.values()),
                    "tokens": sum(
                        (turn.get("usage") or {}).get(k, 0)
                        for turn in turns
                        for k in ("input", "output")
                    ),
                    "steps": len(turns)
                    + sum(e["type"] == "turn.auditing" for e in events),
                    "api_errors": 0,
                    "rate_limited": 0,
                }
            if current["status"] == "paused":
                work = self.request("GET", f"/api/sessions/{sid}/work")
                decisions = any(
                    r["state"] == "awaiting_review" for r in work.get("change", [])
                ) or any(r["state"] == "pending" for r in work.get("approval", []))
                if not decisions:
                    # Native observation and server-created continuations can settle without a tab.
                    self.sleep(0.25)
                    continue
            if current["status"] == "paused" or status.get("execution", {}).get(
                "pendingApprovals"
            ):
                self.request("POST", f"/api/sessions/{sid}/cancel")
                raise RuntimeError(
                    f"Exam waiting for an owner decision in app session {sid}"
                )
            self.sleep(0.25)
        self.request("POST", f"/api/sessions/{sid}/cancel")
        raise TimeoutError(
            f"App exam deadline reached in session {sid}; no operation was resubmitted"
        )
