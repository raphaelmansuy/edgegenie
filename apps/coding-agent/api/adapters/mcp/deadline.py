"""Bound legacy sync tool calls at the transport boundary and report refusals as failed calls."""
from __future__ import annotations
import asyncio
import json


async def invoke(fn, *args, deadline: float = 30, **kwargs):
    try:
        result = await asyncio.wait_for(asyncio.to_thread(fn, *args, **kwargs), deadline)
    except TimeoutError:
        # Cancelling the waiter cannot cancel a remote effect. Never claim it failed to execute.
        raise RuntimeError("Tool deadline reached; outcome unknown. Do not repeat a mutation. "
                           "Observe the native handle or ask the owner to reconcile it.") from None
    try:
        body = json.loads(result) if isinstance(result, str) else result
    except ValueError:
        return result
    if isinstance(body, dict) and body.get('error'):
        raise RuntimeError(str(body['error']))
    return result
