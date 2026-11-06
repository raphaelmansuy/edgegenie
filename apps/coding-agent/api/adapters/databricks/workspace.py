"""Browse and read the Databricks workspace with the *user's* token.

The tree in the UI is the real workspace: notebooks, files, folders and repos, as workspace
permissions allow for the signed-in user. Nothing here is cached across users.

Rules learned from the rest of this app:
  * one directory per call (lazy loading): a workspace can hold thousands of objects and the browser
    must not be sent a whole tree it will not look at;
  * a failure is reported, never swallowed: a folder that cannot be read says so;
  * search is bounded (depth, breadth, time) because the workspace API has no server-side search.
"""
from __future__ import annotations

import asyncio
import base64
import time
from dataclasses import dataclass, field
from typing import Any

from ...domain import notebook as nb
from .http import DbxHttp

# Notebooks appear in the tree as leaves; the kind tells the UI which icon to draw.
KIND = {"NOTEBOOK": "notebook", "FILE": "file", "DIRECTORY": "directory", "REPO": "repo", "LIBRARY": "library"}
FOLDERS = ("directory", "repo")

MAX_READ_BYTES = 400_000          # what the viewer shows; the agent has its own paged reader
SEARCH_MAX_DEPTH = 4
SEARCH_MAX_DIRS = 120
SEARCH_BUDGET_SECONDS = 8.0
SEARCH_MAX_RESULTS = 40


@dataclass(slots=True)
class Node:
    path: str
    name: str
    kind: str
    language: str = ""
    object_id: str = ""
    children: list["Node"] = field(default_factory=list)
    has_children: bool = False
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"path": self.path, "name": self.name, "kind": self.kind,
                               "hasChildren": self.has_children}
        if self.language:
            out["language"] = self.language
        if self.object_id:
            out["objectId"] = self.object_id
        if self.error:
            out["error"] = self.error
        if self.children:
            out["children"] = [c.to_dict() for c in self.children]
        return out


@dataclass(slots=True)
class WorkspaceObject:
    """A notebook or file, read for display."""

    path: str
    kind: str
    language: str
    size: int
    truncated: bool
    cells: list[nb.Cell]
    text: str = ""
    object_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"objectId": self.object_id, "path": self.path, "name": self.path.rsplit("/", 1)[-1], "kind": self.kind,
                "language": self.language, "size": self.size, "truncated": self.truncated,
                "cells": [c.to_dict() for c in self.cells], "text": self.text}


def _node(o: dict) -> Node:
    kind = KIND.get(str(o.get("object_type", "")).upper(), "file")
    path = o.get("path", "")
    return Node(path=path, name=str(path).rsplit("/", 1)[-1], kind=kind,
                language=str(o.get("language") or ""), object_id=str(o.get("object_id") or ""),
                has_children=kind in FOLDERS)


def _sorted(nodes: list[Node]) -> list[Node]:
    # folders first, then alphabetical: the order people expect in a file tree
    return sorted(nodes, key=lambda n: (n.kind not in FOLDERS, n.name.lower()))


class WorkspaceBrowser:
    """Thin client for the workspace REST API."""

    def __init__(self, host: str, token_provider, http: DbxHttp | None = None) -> None:
        self._http = http or DbxHttp(host, token_provider)

    async def list_dir(self, path: str, token: str | None) -> list[Node]:
        try:
            data = await self._http.get("/api/2.0/workspace/list", token, {"path": path})
        except LookupError:
            return []
        return _sorted([_node(o) for o in (data or {}).get("objects") or []])

    async def tree(self, path: str, token: str | None, depth: int = 1) -> Node:
        """One node with `depth` levels of children below it."""
        root = Node(path=path, name=path.rstrip("/").rsplit("/", 1)[-1] or "Workspace", kind="directory",
                    has_children=True)
        root.children = await self.list_dir(path, token)
        if depth > 1:
            expandable = [c for c in root.children if c.has_children][:20]
            await asyncio.gather(*(self._fill(c, token, depth - 1) for c in expandable))
        return root

    async def _fill(self, node: Node, token: str | None, depth: int) -> None:
        try:
            node.children = await self.list_dir(node.path, token)
        except (PermissionError, RuntimeError) as exc:
            node.error = str(exc)[:200]
            node.has_children = False
            return
        if depth > 1:
            await asyncio.gather(*(self._fill(c, token, depth - 1) for c in node.children if c.has_children))

    # -- reading ---------------------------------------------------------------------------
    async def read(self, path: str, token: str | None) -> WorkspaceObject:
        """Export a notebook (as cells) or a file (as text). Permission and absence propagate."""
        status, exported = await asyncio.gather(
            self._http.get("/api/2.0/workspace/get-status", token, {"path": path}),
            self._http.get("/api/2.0/workspace/export", token, {"path": path, "format": "SOURCE"}),
        )
        kind = KIND.get(str(status.get("object_type", "")).upper(), "file")
        if kind in FOLDERS:
            raise IsADirectoryError(f"{path} is a folder")
        raw = base64.b64decode(exported.get("content", "") or "")
        size = int(status.get("size") or len(raw))
        truncated = len(raw) > MAX_READ_BYTES
        text = raw[:MAX_READ_BYTES].decode("utf-8", "replace")
        language = str(status.get("language") or "").upper()
        oid = str(status.get("object_id") or "")
        if kind == "notebook":
            return WorkspaceObject(path, kind, language, size, truncated, nb.parse_source(text, language),
                                   object_id=oid)
        return WorkspaceObject(path, kind, language, size, truncated, [], text, oid)

    # -- searching -------------------------------------------------------------------------
    async def search(self, root: str, query: str, token: str | None) -> tuple[list[Node], bool]:
        """Breadth-first name search under `root`. Returns (matches, complete).

        `complete` is False when a bound stopped the walk: the UI must say "showing the first
        matches" instead of implying nothing else exists.
        """
        needle = query.strip().lower()
        if not needle:
            return [], True
        deadline = time.monotonic() + SEARCH_BUDGET_SECONDS
        level = [root]
        hits: list[Node] = []
        visited = 0
        complete = True
        for _depth in range(SEARCH_MAX_DEPTH):
            if not level:
                break
            if time.monotonic() > deadline or visited >= SEARCH_MAX_DIRS:
                complete = False
                break
            batch, level = level[: SEARCH_MAX_DIRS - visited], level[SEARCH_MAX_DIRS - visited:]
            if level:
                complete = False
            visited += len(batch)
            results = await asyncio.gather(*(self.list_dir(p, token) for p in batch), return_exceptions=True)
            nxt: list[str] = []
            for res in results:
                if isinstance(res, PermissionError) and not hits and len(batch) == 1:
                    raise res                       # the root itself is unreadable: say so
                if isinstance(res, BaseException):
                    continue                         # one unreadable subfolder must not hide the rest
                for n in res:
                    if needle in n.name.lower():
                        hits.append(n)
                    if n.has_children and not n.name.startswith("."):
                        nxt.append(n.path)
            if len(hits) >= SEARCH_MAX_RESULTS:
                return hits[:SEARCH_MAX_RESULTS], False
            level = nxt + level
        else:
            complete = complete and not level
        return hits[:SEARCH_MAX_RESULTS], complete

    # -- writing (user-initiated only; the agent has its own fenced tools) -----------------
    async def mkdirs(self, path: str, token: str | None) -> None:
        await self._http.post("/api/2.0/workspace/mkdirs", token, {"path": path})
