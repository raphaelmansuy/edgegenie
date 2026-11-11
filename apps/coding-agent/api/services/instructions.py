"""Read the instructions a session should be told, with the user's own token. I/O only. `[R-17]`.

The merge and the precedence live in `domain/instructions.py` (pure, testable without a workspace); this
module does the three reads and hands back sources — plus a `Missing` for every file that could not be
read, because an agent that did not see the team's rules must not answer as if it had.

**Three locations, and why each:**

    Workspace/.assistant/instructions.md   the team's rules, authored by an admin
    <home>/.assistant/instructions.md      the user's own
    <folder>/AGENTS.md, walking up         the folder's, discovered the way Genie Code discovers it

Reading walks up from the session's folder to the first `AGENTS.md` and stops: a second one further up
would be a different project's conventions, and merging two is how an agent gets told contradictory
things with no way to tell which is nearer.
"""

from __future__ import annotations

import logging

from ..domain.instructions import Missing, Source, merge

log = logging.getLogger("app.instructions")

#: Where the platform keeps personal and workspace instructions. A convention, not a secret.
PERSONAL = ".assistant/instructions.md"
WORKSPACE = "/Workspace/.assistant/instructions.md"
#: How far up from the session's folder to look for AGENTS.md.
MAX_WALK = 4


async def load(workspace, *, folder: str, home: str, token: str | None) -> tuple[list[Source], list[Missing]]:
    """Read every configured source. Never raises: a missing file is a `Missing`, not an exception.

    `workspace` is the `WorkspaceBrowser` port, so this needs no vendor SDK and a test passes a fake.
    """
    sources: list[Source] = []
    missing: list[Missing] = []
    if not token:
        # No credential means no read. Reported once rather than three times, because the reason is one
        # reason and a reader does not need it repeated per path.
        return sources, [Missing("workspace", WORKSPACE, "no workspace credential for this request")]

    for kind, path in (("workspace", WORKSPACE), ("personal", f"{home.rstrip('/')}/{PERSONAL}")):
        text = await _read(workspace, path, token)
        if text is None:
            # An absent file is normal — most workspaces have none — so it is recorded but quiet.
            continue
        if isinstance(text, str):
            sources.append(Source(kind, text, path))
        else:
            missing.append(Missing(kind, path, text.reason))

    found = await _find_agents_md(workspace, folder, token)
    if isinstance(found, tuple):
        path, text = found
        sources.append(Source("agents_md", text, path))
    elif found is not None:
        missing.append(Missing("agents_md", found.path, found.reason))
    return sources, missing


class Unreadable:
    """A path that exists but could not be read. Distinct from absent, which is normal."""

    def __init__(self, path: str, reason: str) -> None:
        self.path, self.reason = path, reason


async def _read(workspace, path: str, token: str | None) -> str | Unreadable | None:
    """One file, or `None` when it is simply absent, or `Unreadable` when it exists and failed.

    The three outcomes are distinct on purpose: "you have no instructions" and "your instructions could
    not be read" produce different advice, and collapsing them would hide a permission problem behind a
    sentence that looks like a configuration choice.
    """
    try:
        obj = await workspace.read(path, token)
    except PermissionError as exc:
        return Unreadable(path, f"permission denied: {str(exc)[:120]}")
    except (LookupError, IsADirectoryError):
        return None
    except Exception as exc:  # noqa: BLE001 - one unreadable file must not fail the session
        log.debug("could not read %s: %s", path, exc)
        return Unreadable(path, type(exc).__name__)
    text = getattr(obj, "text", "") or ""
    return text if text.strip() else None


async def _find_agents_md(workspace, folder: str, token: str | None):
    """Walk up from `folder` to the first AGENTS.md. One result: the nearest file wins."""
    parts = [p for p in (folder or "").strip("/").split("/") if p]
    for depth in range(min(MAX_WALK, len(parts)) + 1):
        base = "/" + "/".join(parts[: len(parts) - depth]) if depth else "/" + "/".join(parts)
        path = f"{base.rstrip('/')}/AGENTS.md" if base.strip("/") else "/AGENTS.md"
        text = await _read(workspace, path, token)
        if text is None:
            continue
        if isinstance(text, str):
            return path, text
        return text  # an Unreadable: stop and report rather than jumping to a parent's rules
    return None


def render(sources: list[Source], missing: list[Missing], *, scope: str):
    """Merge for the prompt. A thin wrapper so a caller does not import the domain module directly."""
    return merge(sources, scope=scope, missing=missing)
