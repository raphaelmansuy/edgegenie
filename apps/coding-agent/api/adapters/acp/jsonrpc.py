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
        self._notify_task = asyncio.create_task(self._dispatch_notifications())
        self.closed = False

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
        for t in (self._reader_task, self._notify_task):
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

    async def _read_loop(self) -> None:
        try:
            while True:
                line = await self._r.readline()
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
                self._route(msg)
        except asyncio.CancelledError:
            pass
        finally:
            self.closed = True
            for fut in self._pending.values():
                if not fut.done():
                    fut.set_exception(TransportError("agent process ended"))
            await self._notifications.put({"method": "$/closed", "params": {}})

    def _route(self, msg: dict) -> None:
        if "id" in msg and ("result" in msg or "error" in msg):
            fut = self._pending.get(msg["id"])
            if fut and not fut.done():
                fut.set_result(msg)
            return
        if "id" in msg and "method" in msg:  # agent -> client request
            asyncio.create_task(self._serve_request(msg))
            return
        if "method" in msg:  # notification
            try:
                self._notifications.put_nowait(msg)
            except asyncio.QueueFull:
                pass  # drop under extreme back-pressure rather than block the reader

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
            self._write({"jsonrpc": "2.0", "id": msg["id"], "result": result})
        except Exception as exc:  # noqa: BLE001 - never leave the agent waiting
            self._write(
                {"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32603, "message": str(exc)[:200]}}
            )

    async def _dispatch_notifications(self) -> None:
        """Keep reader order: notifications are consumed by events(); this task exists so
        the queue is never blocked by an idle consumer. Consumers call next_notification."""
        try:
            await asyncio.Event().wait()  # parked; next_notification pulls directly
        except asyncio.CancelledError:
            pass
