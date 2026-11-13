"""Notebook/file assets. Plans preserve raw SOURCE bytes and recheck both identity and content."""

import difflib
from ....domain.asset import Actor, AssetRef, AssetContent, Plan, WorkError, digest
from ....domain.edits import cells, edit_cells, edit_ranges, MAX_SOURCE
from ....domain.policy.paths import inside
from ....domain.policy.verdict import ActionClass


class WorkspaceHandler:
    def __init__(self, workspace, kind):
        self.workspace, self.kind = workspace, kind
        self._exports = {}

    def invalidate(self, ref, who):
        self._exports = {k: v for k, v in self._exports.items() if k[:2] != (who.session_id, ref.id)}

    def inside(self, ref, who):
        return inside(ref.id, who.scope.folder)

    async def probe(self, who):
        await self.workspace.list_dir(who.scope.folder, who.token)
        return {
            "read": True,
            "change": True,
            "run": False,
            "tier": "api",
            "reason": "Workspace access as you; agent Python runs require a separate identity.",
        }

    async def read(self, ref: AssetRef, who: Actor) -> AssetContent:
        info = await self.workspace.status(ref.id, who.token)
        key = (who.session_id, ref.id, who.turn_id, info.get("object_id"), info.get("modified_at"))
        if who.turn_id and info.get("modified_at") is not None and key in self._exports:
            return self._exports[key]
        raw = await self.workspace.export_content(ref.id, who.token, "SOURCE")
        if len(raw) > MAX_SOURCE:
            raise WorkError("This source exceeds the 4 MiB agent editing limit.", 422)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise WorkError("Binary content cannot be edited by this tool.", 422) from None
        expected = "NOTEBOOK" if self.kind == "notebook" else "FILE"
        if info.get("object_type") and info["object_type"] != expected:
            raise WorkError("The asset kind changed. Read it using its current kind.")
        revision = digest([str(info.get("object_id", "")), info.get("modified_at"), digest(text)])
        value = AssetContent(ref, revision, text, str(info.get("language") or "PYTHON"), info)
        if who.turn_id and info.get("modified_at") is not None:
            if len(self._exports) >= 128:
                self._exports.clear()
            self._exports[key] = value
        return value

    def cell_index(self, value):
        if self.kind != "notebook":
            return []
        _, parts, _ = cells(value.content)
        result, remaining = [], 6000
        for i, part in enumerate(parts[:100]):
            source = part[: min(2000, remaining)]
            remaining -= len(source)
            result.append(
                {
                    "index": i,
                    "sha": digest(part),
                    "source": source,
                    "characters": len(part),
                    "truncated": len(source) < len(part),
                }
            )
        return result

    def read_fragment(self, value, *, cell=None):
        """Own the kind-specific selection and manifest used by every tool caller."""
        if cell is not None:
            if self.kind != "notebook" or isinstance(cell, bool) or not isinstance(cell, int):
                raise WorkError("cell selects a zero-based notebook cell only.", 422)
            _, parts, _ = cells(value.content)
            if cell < 0 or cell >= len(parts):
                raise WorkError("The requested notebook cell does not exist.", 422)
            return parts[cell], {
                "cellOnly": True,
                "cell": cell,
                "totalCells": len(parts),
                "cells": [{"index": cell, "sha": digest(parts[cell])}],
            }
        if self.kind == "notebook":
            total = len(cells(value.content)[1])
            index = self.cell_index(value)
            return value.content, {"cells": index, "totalCells": total, "cellsCapped": len(index) < total}
        return value.content, {}

    async def describe(self, ref, who):
        value = await self.read(ref, who)
        result = {
            "asset": ref.to_dict(),
            "revision": value.revision,
            "language": value.language,
            "bytes": len(value.content.encode()),
        }
        if self.kind == "notebook":
            _, parts, _ = cells(value.content)
            result["cells"] = [
                {"index": i, "sha": digest(p), "characters": len(p)} for i, p in enumerate(parts)
            ]
        return result

    async def find_under(self, root, query, who):
        return await self.workspace.search(root, query, who.token)

    async def find(self, query, who, limit):
        found, complete = await self.workspace.search(who.scope.folder, query, who.token)
        return [
            {"kind": self.kind, "id": n.path, "name": n.name, "capped": not complete}
            for n in found
            if n.kind == self.kind
        ][: min(limit, 100)]

    def render_edit(self, source, operations, language="PYTHON"):
        return (
            edit_cells(source, operations, language)
            if self.kind == "notebook"
            else edit_ranges(source, operations)
        )

    async def plan(self, ref, base, operations, who, *, content=None):
        try:
            current = await self.read(ref, who)
        except LookupError:
            current = AssetContent(ref, "", "", "PYTHON" if self.kind == "notebook" else "")
        if current.revision != base:
            raise WorkError(
                "The asset changed after it was read. Nothing was written.", current=current.revision
            )
        if not base and content is None:
            raise WorkError("A create requires content; an edit requires a base revision.", 422)
        if base and content is not None:
            raise WorkError(
                "Existing source must be edited by cell or range operations, without whole-document content.",
                422,
            )
        if base and not operations:
            raise WorkError("Edit an existing asset with operations and its base revision.", 422)
        after = (
            content
            if content is not None
            else self.render_edit(current.content, operations, current.language)
        )
        if not isinstance(after, str) or len(after.encode()) > MAX_SOURCE:
            raise WorkError("Source exceeds 4 MiB.", 422)
        can_undo = bool(base) and len(current.content.encode()) <= 2 * 1024 * 1024
        diff = "".join(
            difflib.unified_diff(
                current.content.splitlines(True),
                after.splitlines(True),
                fromfile="current",
                tofile="proposed",
            )
        )
        return Plan(
            ref,
            base,
            current.content,
            after,
            operations,
            diff[:65536],
            ActionClass.CHANGE if not base or can_undo else ActionClass.IRREVERSIBLE,
            current.language,
            can_undo,
            "edit" if base else "create",
        )

    async def apply(self, plan, who):
        self.invalidate(plan.ref, who)
        try:
            current = await self.read(plan.ref, who)
        except LookupError:
            current = AssetContent(plan.ref, "", "")
        if current.revision != plan.base:
            raise WorkError(
                "The asset changed after the proposal. Nothing was written.", current=current.revision
            )
        await self.workspace.mkdirs(plan.ref.id.rsplit("/", 1)[0], who.token)
        await self.workspace.import_content(
            plan.ref.id,
            plan.after.encode(),
            who.token,
            format="SOURCE" if self.kind == "notebook" else "AUTO",
            language=plan.language if self.kind == "notebook" else "",
            overwrite=bool(plan.base),
        )
        self.invalidate(plan.ref, who)
        actual = await self.read(plan.ref, who)
        if actual.content != plan.after:
            raise WorkError(
                "Read-back differs from the approved change. Review the current version.",
                current=actual.revision,
            )
        return actual

    async def restore(self, ref, expect, content, who, language):
        current = await self.read(ref, who)
        if current.revision != expect:
            raise WorkError("Undo refused: the asset changed after this change.", current=current.revision)
        plan = Plan(ref, expect, current.content, content, [], "", language=language)
        return await self.apply(plan, who)

    async def remove(self, ref, expect, who):
        self.invalidate(ref, who)
        current = await self.read(ref, who)
        if current.revision != expect:
            raise WorkError("Cleanup refused: the asset revision changed.", current=current.revision)
        await self.workspace.remove(ref.id, who.token, recursive=False)
