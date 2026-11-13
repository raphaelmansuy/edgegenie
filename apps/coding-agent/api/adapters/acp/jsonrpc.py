"""Newline-delimited JSON-RPC over a child process's stdio.

Deliberately small: framing, ids, timeouts, and the ability to receive agent-initiated
requests (like session/request_permission) while the client waits for a response.
One read can contain several messages, and one message can be split across reads:
both are handled by buffering on newlines, never by assuming one message per read.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

Handler = Callable[[dict], Awaitable[Any]]
MAX_LINE = 16 * 1024 * 1024


class TransportError(Exception):
    pass


class Channel(Protocol):
    async def request(self, method: str, params: dict, timeout: float | None = 30) -> dict: ...
    def notify(self, method: str, params: dict) -> None: ...
    async def close(self) -> None: ...
    def on_request(self, method: str, handler: Handler) -> None: ...


class StdioChannel:
    """A JSON-RPC channel over an already-spawned process."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._r = reader
        self._w = writer
        self._next_id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._handlers: dict[str, Handler] = {}
        self._notifications: asyncio.Queue[dict] = asyncio.Queue(maxsize=10_000)
        self._reader_task = asyncio.create_task(self._read_loop())
        self.closed = False
        self._discard_history = False

    # -- public ---------------------------------------------------------------
    def on_request(self, method: str, handler: Handler) -> None:
        self._handlers[method] = handler

    async def request(self, method: str, params: dict, timeout: float | None = 30) -> dict:
        self._next_id += 1
        rid = self._next_id
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[rid] = fut
        self._write({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        try:
            msg = await asyncio.wait_for(fut, timeout) if timeout else await fut
        except TimeoutError as exc:
            raise TransportError(f"{method} timed out after {timeout}s") from exc
        finally:
            self._pending.pop(rid, None)
        if "error" in msg:
            raise TransportError(f"{method} failed: {json.dumps(msg['error'])[:400]}")
        return msg.get("result", {})

    def notify(self, method: str, params: dict) -> None:
        self._write({"jsonrpc": "2.0", "method": method, "params": params})

    def discard_session_history(self, enabled: bool) -> None:
        """During session/load the caller already has this history in its own journal."""
        self._discard_history = enabled

    async def enqueue_notification(self, message: dict) -> None:
        if self._notifications.full():
            self._notifications.get_nowait()
        self._notifications.put_nowait(message)

    def next_notification_nowait(self) -> dict:
        """Non-blocking read of an already-delivered notification. Raises LookupError when empty."""
        try:
            return self._notifications.get_nowait()
        except asyncio.QueueEmpty as exc:
            raise LookupError("no queued notification") from exc

    async def next_notification(self, timeout: float | None = None) -> dict:
        if timeout:
            return await asyncio.wait_for(self._notifications.get(), timeout)
        return await self._notifications.get()

    async def close(self) -> None:
        self.closed = True
        for t in (self._reader_task,):
            t.cancel()
        try:
            self._w.close()
        except Exception:  # noqa: BLE001 - closing a dead pipe must not raise
            pass

    # -- internals ------------------------------------------------------------
    def _write(self, obj: dict) -> None:
        if self.closed:
            raise TransportError("channel closed")
        self._w.write((json.dumps(obj) + "\n").encode())
        # write() on a StreamWriter is buffered; drain asynchronously to keep ordering
        asyncio.create_task(self._drain())

    async def _drain(self) -> None:
        try:
            await self._w.drain()
        except (ConnectionResetError, BrokenPipeError):
            self.closed = True

    async def _read_frame(self) -> bytes:
        """Discard only the offending frame, even when it arrives in multiple chunks."""
        oversized = False
        while True:
            try:
                line = await self._r.readuntil(b"\n")
            except asyncio.LimitOverrunError as exc:
                await self._r.readexactly(exc.consumed)
                oversized = True
                continue
            except asyncio.IncompleteReadError:
                return b""
            if oversized or len(line) > MAX_LINE:
                await self.enqueue_notification(
                    {"method": "$/notice", "params": {"message": "Skipped an over-limit ACP frame"}}
                )
                oversized = False
                continue
            return line

    async def _read_loop(self) -> None:
        try:
            while True:
                line = await self._read_frame()
                if not line:
                    break
                if len(line) > MAX_LINE:
                    continue
                text = line.decode(errors="replace").strip()
                if not text:
                    continue
                try:
                    msg = json.loads(text)
                except json.JSONDecodeError:
                    continue  # agent noise on stdout must never kill the session
                if isinstance(msg, dict):
                    await self._route(msg)
        except asyncio.CancelledError:
            pass
        finally:
            self.closed = True
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(TransportError("agent process ended"))
            await self.enqueue_notification({"method": "$/closed", "params": {}})

    async def _route(self, msg: dict) -> None:
        if "id" in msg and ("result" in msg or "error" in msg):
            fut = self._pending.get(msg["id"])
            if fut and not fut.done():
                fut.set_result(msg)
            return
        if "id" in msg and "method" in msg:  # agent -> client request
            asyncio.create_task(self._serve_request(msg))
            return
        if "method" in msg:  # notification
            if self._discard_history and msg["method"] == "session/update":
                return
            await self.enqueue_notification(msg)

    async def _serve_request(self, msg: dict) -> None:
        handler = self._handlers.get(msg["method"])
        if handler is None:
            self._write(
                {
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "error": {"code": -32601, "message": f"no handler for {msg['method']}"},
                }
            )
            return
        try:
            result = await handler(msg.get("params", {}))
            if self.closed:
                return
            self._write({"jsonrpc": "2.0", "id": msg["id"], "result": result})
        except Exception as exc:  # noqa: BLE001 - never leave the agent waiting
            if self.closed:
                return
            self._write(
                {
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "error": {
                        "code": -32602 if isinstance(exc, ValueError) else -32603,
                        "message": str(exc)[:200],
                    },
                }
            )
