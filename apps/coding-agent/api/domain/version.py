"""A version token for a workspace object: what the client held, compared on save.

The workspace API has no conditional write (no `If-Match`), so optimistic concurrency has to be
assembled from observations. The observations available are `object_id`, `modified_at` and `size`
from `get-status`. This module turns them into one opaque token and compares tokens, so the rest of
the system never has to know which fields went into it.

Two rules:

  * **The token must change whenever the content could have changed.** `modified_at` gives that.
  * **The token must not change when nothing changed.** Otherwise every save conflicts with itself.
    A refresh alone does not bump `modified_at`, which is what makes the token usable.

`size` is included because a same-millisecond rewrite with identical length is the one case
`modified_at` cannot distinguish, and it costs nothing.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Version:
    """The identity of one revision of an object."""

    token: str
    modified_at: int
    size: int

    def to_dict(self) -> dict[str, Any]:
        return {"token": self.token, "modifiedAt": self.modified_at, "size": self.size}


def of(status: dict[str, Any] | None) -> Version | None:
    """Build a token from a `get-status` payload. `None` when the payload has nothing to go on.

    A missing token must never be silently treated as "current": that would turn every conflict
    into an overwrite. `None` forces the caller to decide, and the save route treats it as "no
    version supplied" rather than "matches".

    **`object_id` is deliberately not part of the token.** The only way to overwrite a notebook in
    SOURCE format is delete-then-import (the API refuses `overwrite` with `format=SOURCE`), and that
    mints a new `object_id` every time. Including it would make a token stale the moment it was
    written, so every first save would 409 — which is exactly what happened before this comment
    existed. What actually changes when the content changes is `modified_at` and `size`, and those
    are what the token hashes.
    """
    if not status:
        return None
    modified = status.get("modified_at")
    size = status.get("size")
    if modified is None and size is None:
        return None
    # A token is a digest so that callers cannot read meaning into it and start comparing fields.
    raw = f"{modified if modified is not None else ''}|{size if size is not None else ''}"
    token = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]
    return Version(token=token, modified_at=int(modified or 0), size=int(size or 0))


def matches(current: Version | None, held: str | None) -> bool:
    """Does the version the client held still describe the object on the server?

    Absent information is *not* a match: if either side is unknown, the caller cannot claim the
    object is unchanged, and should fall through to the conflict path rather than overwrite.
    """
    if current is None or not held:
        return False
    return current.token == held
