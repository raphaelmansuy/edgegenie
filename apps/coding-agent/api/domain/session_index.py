"""Small session headers and stable owner-scoped pagination shared by journal adapters."""

import base64
import json
import time


def header(snapshot):
    return {**snapshot["session"], "updatedAt": time.time()}


def cursor_encode(updated, sid):
    return base64.urlsafe_b64encode(json.dumps([updated, sid]).encode()).decode()


def cursor_decode(cursor):
    if not cursor:
        return None
    try:
        stamp, sid = json.loads(base64.urlsafe_b64decode(cursor))
        if not isinstance(stamp, (float, int)) or not isinstance(sid, str):
            raise ValueError()
        return stamp, sid
    except Exception:
        raise ValueError("Invalid session cursor") from None
