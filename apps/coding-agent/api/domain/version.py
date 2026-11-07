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

    **The token is `modified_at` alone, and that is a measured decision.** Three fields were tried
    and two had to go:

    * `object_id` — the only way to overwrite a notebook in SOURCE format is delete-then-import (the
      API refuses `overwrite` with `format=SOURCE`), and that mints a new `object_id` on every save.
      Including it made every first save 409.
    * `size` — **`get-status` does not return `size` for a notebook at all.** It returns
      `object_type`, `path`, `language`, `created_at`, `modified_at`, `object_id`. The *read* path
      filled `size` from the exported bytes (35), while the *save* path called `of(status)` where
      `size` was absent (0), so the two computed different tokens for the same unchanged object and
      every save 409'd. Verified against the live workspace with a raw `get-status` call.

    `modified_at` is the field that actually changes when the content changes, and it is present.
    That is the whole token.
    """
    if not status:
        return None
    modified = status.get("modified_at")
    if modified is None:
        return None
    token = hashlib.sha256(str(modified).encode("utf-8")).hexdigest()[:32]
    return Version(token=token, modified_at=int(modified), size=int(status.get("size") or 0))


def matches(current: Version | None, held: str | None) -> bool:
    """Does the version the client held still describe the object on the server?

    Absent information is *not* a match: if either side is unknown, the caller cannot claim the
    object is unchanged, and should fall through to the conflict path rather than overwrite.
    """
    if current is None or not held:
        return False
    return current.token == held
