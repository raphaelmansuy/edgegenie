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
from urllib.parse import quote
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
    #: Epoch seconds from get-status. Carried so the client can hold a version token for the save
    #: path (spec 003 CX-1) without a second round trip.
    modified_at: int = 0
    incomplete_reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"objectId": self.object_id, "path": self.path, "name": self.path.rsplit("/", 1)[-1], "kind": self.kind,
                "language": self.language, "size": self.size, "truncated": self.truncated,
                "incompleteReasons": self.incomplete_reasons,
                "modifiedAt": self.modified_at,
                # The version token itself, so the client never re-derives it. Two derivations of
                # one token is a guaranteed false-conflict bug: the client's hash will not equal
                # the server's, so every first save would be refused.
                "version": _version_token(self.object_id, self.modified_at, self.size),
                "cells": [c.to_dict() for c in self.cells], "text": self.text}


def _version_token(_object_id: str, modified_at: int, _size: int) -> str:
    """The same token the save route computes, from the same one field.

    The arguments beyond `modified_at` are kept so call sites read clearly, but only
    `modified_at` is hashed — see `api.domain.version.of` for why `object_id` and `size` had to be
    excluded (the first is recreated by delete-then-import, the second is absent from `get-status`
    for a notebook, and including either made every save 409).
    """
    from ...domain.version import of as version_of
    v = version_of({"modified_at": modified_at})
    return v.token if v else ""


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
        modified = int(status.get("modified_at") or 0)
        if kind == "notebook":
            cells, reasons = nb.read_completeness(text, language)
            if truncated:
                reasons.insert(0, "document_bytes")
            return WorkspaceObject(path, kind, language, size, bool(reasons), cells,
                                   object_id=oid, modified_at=modified, incomplete_reasons=reasons)
        return WorkspaceObject(path, kind, language, size, truncated, [], text, oid, modified)

    # -- searching -------------------------------------------------------------------------
    async def markdown_image(self, path: str, token: str) -> tuple[bytes, str]:
        from ...domain.markdown_media import MAX_BYTES, validate_raster
        if not token:
            raise PermissionError("image loading requires your user authorization")
        if not path.startswith(("/Workspace/", "/Users/", "/Shared/", "/Repos/", "/Volumes/")) or any(p in (".", "..") for p in path.split("/")):
            raise ValueError("image must be a canonical workspace or volume path")
        if path.startswith("/Volumes/"):
            raw = await self._http.get_bytes("/api/2.0/fs/files" + quote(path, safe="/"), token, limit=MAX_BYTES)
        else:
            raw = await self._http.get_bytes("/api/2.0/workspace/export", token,
                                             params={"path": path, "format": "AUTO", "direct_download": "true"}, limit=MAX_BYTES)
        return raw, validate_raster(raw)

    async def ensure_complete_notebook(self, path: str, text: str, language: str, token: str | None,
                                       *, existing: bool) -> None:
        """Reject partial editor writes before import can replace the original notebook."""
        if len(text.encode("utf-8")) > MAX_READ_BYTES:
            raise ValueError("notebook exceeds the editor's 400,000 byte limit")
        _, reasons = nb.read_completeness(text, language)
        if reasons:
            raise ValueError("notebook exceeds the editor's cell count or cell source limits")
        if existing:
            current = await self.read(path, token)
            if current.truncated or any(c.truncated for c in current.cells):
                raise ValueError("the original notebook is incomplete in this editor; open it in Databricks to preserve its full content")

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

    async def status(self, path: str, token: str | None) -> dict[str, Any]:
        """`get-status` as a plain dict: object_id, modified_at, size, language, object_type.

        Exposed because the save path needs the *version* of an object (see domain/version.py) and
        `read()` throws that away in favour of the content.
        """
        return await self._http.get("/api/2.0/workspace/get-status", token, {"path": path})

    async def import_source(self, path: str, text: str, token: str | None, *,
                            language: str = "", overwrite: bool = True) -> dict[str, Any]:
        """Write a notebook or file in SOURCE format, as the signed-in user.

        Measured on the workspace API: **`overwrite` is rejected together with `format=SOURCE`** —
        `INVALID_PARAMETER_VALUE: Overwrite cannot be used for SOURCE format when importing a
        folder.` So an overwrite is not a flag here, it is two calls: delete the object, then import
        it. That is also the only ordering that is safe, because a failed import after a successful
        delete leaves *nothing* rather than a half-written object — and the caller holds a local
        draft, so nothing is lost (spec 003 CX-5).

        `format=SOURCE` is the only format that keeps a notebook as text both ways: it is what
        `read()` exports and what `parse_source` understands. `language` is passed on a create and
        omitted on overwrite, so an existing notebook keeps its language; sending a different one is
        how a Python notebook silently becomes a SQL one.
        """
        body: dict[str, Any] = {
            "path": path,
            "format": "SOURCE",
            "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
        }
        # `language` is not optional in practice for SOURCE: after a delete the API has no object to
        # infer from, and responds "The zip archive contains no items." (measured). So the caller
        # always supplies it, and the route falls back to the language the object had.
        if language:
            body["language"] = language
        if overwrite:
            # Deleting first is what makes the write an overwrite. A missing object is fine: this is
            # then a create, which is the same end state.
            try:
                await self._http.post("/api/2.0/workspace/delete", token, {"path": path, "recursive": False})
            except LookupError:
                pass
        return await self._http.post("/api/2.0/workspace/import", token, body)

    # -- user actions from the right-click menu (never the agent's tools) -------------------
    #: A right-click must not walk a whole workspace. Past this, the user is sent to Databricks.
    MAX_COPY_OBJECTS = 200
    MAX_COPY_DEPTH = 8
    MAX_EXPORT_BYTES = 25_000_000

    async def exists(self, path: str, token: str | None) -> bool:
        try:
            await self.status(path, token)
        except LookupError:
            return False
        return True

    async def remove(self, path: str, token: str | None, *, recursive: bool) -> None:
        """Move an object to the workspace trash. `recursive` is required by the API for a folder."""
        await self._http.post("/api/2.0/workspace/delete", token, {"path": path, "recursive": recursive})

    async def export_content(self, path: str, token: str | None, format: str) -> bytes:
        data = await self._http.get("/api/2.0/workspace/export", token, {"path": path, "format": format})
        raw = base64.b64decode((data or {}).get("content") or "")
        if len(raw) > self.MAX_EXPORT_BYTES:
            raise ValueError("this object is too large to handle here; open it in Databricks")
        return raw

    async def import_content(self, path: str, raw: bytes, token: str | None, *,
                              format: str, language: str = "", overwrite: bool = False) -> None:
        """Create an object. Never deletes: a right-click create must not be an overwrite."""
        if len(raw) > self.MAX_EXPORT_BYTES:
            raise ValueError("this file is too large to import here; open it in Databricks")
        body: dict[str, Any] = {
            "path": path, "format": format,
            "content": base64.b64encode(raw).decode("ascii"),
            "overwrite": overwrite,
        }
        if language:
            body["language"] = language
        await self._http.post("/api/2.0/workspace/import", token, body)

    async def permissions(self, path: str, token: str | None) -> list[dict[str, Any]]:
        """Who can see this object, as the permissions API reports it. Read only."""
        status = await self.status(path, token)
        kind = KIND.get(str(status.get("object_type", "")).upper(), "file")
        object_type = {"notebook": "notebooks", "directory": "directories", "repo": "repos"}.get(kind, "files")
        oid = str(status.get("object_id") or "")
        if not oid:
            raise LookupError(f"no object id for {path}")
        data = await self._http.get(f"/api/2.0/permissions/{object_type}/{oid}", token)
        rows: list[dict[str, Any]] = []
        for ace in (data or {}).get("access_control_list") or []:
            who = ace.get("user_name") or ace.get("group_name") or ace.get("service_principal_name") or "unknown"
            principal = "user" if ace.get("user_name") else "group" if ace.get("group_name") else "service"
            for perm in ace.get("all_permissions") or []:
                rows.append({
                    "who": who, "principal": principal,
                    "permission": perm.get("permission_level") or "",
                    "inherited": bool(perm.get("inherited")),
                })
        return rows

    async def relocate(self, source: str, dest: str, token: str | None, *, move: bool) -> None:
        """Copy an object, and delete the original only after the copy has succeeded.

        A folder is copied child by child, so the new folder has the name the user asked for.
        A Databricks archive would keep the old name inside the new one. A Git folder is refused:
        copying its files would drop the repository link, and the user is told to do that in
        Databricks. If the copy fails part way, the new folder is removed and the original stays.
        """
        source = source.rstrip("/") or "/"
        dest = dest.rstrip("/") or "/"
        if source == dest:
            raise ValueError("the destination is the same as the source")
        if dest.startswith(source + "/"):
            raise ValueError("a folder cannot be moved into itself")
        if await self.exists(dest, token):
            raise FileExistsError(f"{dest} already exists")
        status = await self.status(source, token)
        kind = KIND.get(str(status.get("object_type", "")).upper(), "file")
        if kind == "repo":
            raise ValueError("a Git folder keeps its history in Databricks; open it there to rename, move or clone it")
        if kind in FOLDERS:
            try:
                await self._copy_tree(source, dest, token, [self.MAX_COPY_OBJECTS], 0)
            except Exception:
                try:
                    await self.remove(dest, token, recursive=True)
                except LookupError:
                    pass
                raise
            if move:
                await self.remove(source, token, recursive=True)
            return
        await self._copy_leaf(source, dest, token, kind, str(status.get("language") or ""))
        if move:
            await self.remove(source, token, recursive=False)

    async def _copy_tree(self, source: str, dest: str, token: str | None, budget: list[int], depth: int) -> None:
        if depth > self.MAX_COPY_DEPTH:
            raise ValueError("this folder is nested too deeply to copy here; open it in Databricks")
        await self.mkdirs(dest, token)
        for child in await self.list_dir(source, token):
            if budget[0] <= 0:
                raise ValueError("this folder is too large to copy here; open it in Databricks")
            budget[0] -= 1
            target = f"{dest}/{child.name}"
            if child.kind == "repo":
                raise ValueError(f"{child.name} is a Git folder; copy it in Databricks")
            if child.kind in FOLDERS:
                await self._copy_tree(child.path, target, token, budget, depth + 1)
            else:
                st = await self.status(child.path, token)
                await self._copy_leaf(child.path, target, token, child.kind, str(st.get("language") or ""))

    async def _copy_leaf(self, source: str, dest: str, token: str | None, kind: str, language: str) -> None:
        raw = await self.export_content(source, token, "SOURCE")
        if kind == "notebook":
            await self.import_content(dest, raw, token, format="SOURCE", language=language or "PYTHON")
        else:
            await self.import_content(dest, raw, token, format="AUTO")

    async def close(self):
        closer=getattr(self._http,'close',None)
        if closer:await closer()
