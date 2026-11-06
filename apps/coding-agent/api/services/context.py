"""Turn attachment references into text, reading with the user's own token.

Failures are per item: one unreadable attachment must not block the message, and the agent must be
told it was missing rather than left to assume it saw it.
"""
from __future__ import annotations

import asyncio

from ..domain.context import Attachment, Resolved


def _cells_text(obj) -> str:
    return "\n\n".join(f"# --- cell {c.index + 1} ({c.language}) ---\n{c.source}" for c in obj.cells)


async def _one(a: Attachment, ws, cat, token: str | None) -> Resolved:
    try:
        if a.kind in ("notebook", "file"):
            obj = await ws.read(a.ref, token)
            text = _cells_text(obj) if obj.kind == "notebook" else obj.text
            note = f"language {obj.language.lower()}, {len(obj.cells)} cells" if obj.kind == "notebook" else ""
            return Resolved(a, text, note + (" (file larger than the viewer limit)" if obj.truncated else ""))
        if a.kind == "folder":
            kids = await ws.list_dir(a.ref, token)
            lines = [f"{'/' if k.has_children else ''}{k.name}  [{k.kind}]" for k in kids[:80]]
            more = f"\n... and {len(kids) - 80} more" if len(kids) > 80 else ""
            return Resolved(a, "\n".join(lines) + more or "(empty)")
        t = await cat.table(a.ref, token)
        cols = "\n".join(f"  {c['name']} {c['type']}" + (f" -- {c['comment']}" if c["comment"] else "")
                         for c in t["columns"])
        head = f"{t['fullName']} ({t['tableType'].lower() or 'table'})"
        if t["comment"]:
            head += f"\ncomment: {t['comment']}"
        return Resolved(a, f"{head}\ncolumns:\n{cols}")
    except PermissionError as exc:
        return Resolved(a, error=str(exc))
    except (LookupError, IsADirectoryError) as exc:
        return Resolved(a, error=str(exc))
    except Exception as exc:  # noqa: BLE001 - never block a message on an attachment
        return Resolved(a, error=f"{type(exc).__name__}: {str(exc)[:120]}")


async def resolve(items: list[Attachment], ws, cat, token: str | None) -> list[Resolved]:
    return list(await asyncio.gather(*(_one(a, ws, cat, token) for a in items)))
