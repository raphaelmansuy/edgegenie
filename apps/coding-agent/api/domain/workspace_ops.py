"""Rules for the workspace right-click actions. Pure: no HTTP, no FastAPI.

The menu in the browser is allowed to hide a dangerous action. This module is what actually
refuses it, so a hand-built request cannot trash a workspace root the menu has greyed out.
"""

from __future__ import annotations

#: Exact paths the app will not rename, move, clone or trash. Children of these are ordinary objects.
_ROOTS = {"/", "/Users", "/Shared", "/Repos", "/Workspace"}


def is_protected(path: str, home: str) -> bool:
    """A workspace root, the signed-in user's home, or the Repos folder the tree shows first."""
    p = path.rstrip("/") or "/"
    owner = home.removeprefix("/Users/").split("@")[0].replace(".", "_")
    guarded = set(_ROOTS)
    guarded.add(home.rstrip("/") or "/")
    if owner:
        guarded.add(f"/Repos/{owner}")
    return p in guarded


def clean_name(name: str) -> str:
    """One path segment. A slash would let a rename escape the folder the user is looking at."""
    n = name.strip()
    if not n or n in {".", ".."} or "/" in n or "\\" in n or "\x00" in n or len(n) > 200:
        raise ValueError("use a name without slashes")
    return n


def child_path(parent: str, name: str) -> str:
    return f"{parent.rstrip('/')}/{clean_name(name)}"
