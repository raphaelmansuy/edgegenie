"""Browse the Databricks workspace with the *user's* token.

The tree in the UI is the real workspace: notebooks, files, folders and repos, as Unity Catalog
and workspace permissions allow for the signed-in user. Nothing here is cached across users.

Two rules learned from the rest of this app:
  * one directory per call (lazy loading): a workspace can hold thousands of objects and the browser
    must not be sent a whole tree it will not look at;
  * a failure is reported in the node, never swallowed: a folder that cannot be read says so.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import httpx

TIMEOUT = 20.0
# Notebooks appear in the tree as leaves; the kind tells the UI which icon to draw.
KIND = {"NOTEBOOK": "notebook", "FILE": "file", "DIRECTORY": "directory", "REPO": "repo", "LIBRARY": "library"}


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


class WorkspaceBrowser:
    """Thin client for GET /api/2.0/workspace/list."""

    def __init__(self, host: str, token_provider) -> None:
        self._host = host.rstrip("/")
        self._token_provider = token_provider

    async def list_dir(self, path: str, token: str | None) -> list[Node]:
        tok = token or self._token_provider()
        if not tok:
            raise PermissionError(
                "no user token: the workspace tree needs user authorization "
                "(x-forwarded-access-token) or DATABRICKS_TOKEN in development")
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(f"{self._host}/api/2.0/workspace/list",
                                 params={"path": path},
                                 headers={"Authorization": f"Bearer {tok}"})
        if r.status_code == 404:
            return []
        if r.status_code in (401, 403):
            raise PermissionError(f"you do not have access to {path}")
        if r.status_code >= 400:
            raise RuntimeError(f"workspace list failed ({r.status_code}): {r.text[:200]}")

        rows = (r.json() or {}).get("objects") or []
        nodes: list[Node] = []
        for o in rows:
            kind = KIND.get(str(o.get("object_type", "")).upper(), "file")
            nodes.append(Node(path=o.get("path", ""), name=str(o.get("path", "")).rsplit("/", 1)[-1],
                              kind=kind, language=str(o.get("language") or ""),
                              object_id=str(o.get("object_id") or ""),
                              has_children=kind in ("directory", "repo")))
        # folders first, then alphabetical: the order people expect in a file tree
        nodes.sort(key=lambda n: (n.kind not in ("directory", "repo"), n.name.lower()))
        return nodes

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
