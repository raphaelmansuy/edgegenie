"""Durable deterministic workspace double. Enabled only for explicitly configured local agent E2E."""

import time
from uuid import uuid4
from ..databricks.workspace import Node as DemoNode, WorkspaceObject
from ...domain.notebook import parse_source
from ...domain.asset import WorkError, digest


class DemoWorkspace:
    def __init__(self, store):
        self.store = store

    async def _get(self, path):
        try:
            row = await self.store.get("fake_asset", digest(path))
            if row["state"] == "deleted":
                raise LookupError(path)
            return row
        except WorkError:
            raise LookupError(path) from None

    async def seed(self, folder):
        path = folder.rstrip("/") + "/revenue"
        try:
            await self._get(path)
        except LookupError:
            source = "# Databricks notebook source\n" + "\n# COMMAND ----------\n".join(
                f"print({i})\n" for i in range(60)
            )
            await self.import_content(path, source.encode(), None, format="SOURCE", language="PYTHON")
        return path

    async def read(self, path, token):
        row = await self._get(path)
        text = row["content"]
        return WorkspaceObject(
            path,
            row["kind"],
            row["language"],
            len(text.encode()),
            False,
            parse_source(text, row["language"]) if row["kind"] == "notebook" else [],
            text if row["kind"] == "file" else "",
            row["objectId"],
            row["modifiedAt"],
        )

    async def tree(self, path, token, depth=1):
        return DemoNode(
            path,
            path.rsplit("/", 1)[-1],
            "directory",
            children=await self.list_dir(path, token),
            has_children=True,
        )

    async def status(self, path, token):
        row = await self._get(path)
        return {
            "path": path,
            "object_id": row["objectId"],
            "modified_at": row["modifiedAt"],
            "object_type": row["kind"].upper(),
            "language": row["language"],
        }

    async def export_content(self, path, token, format):
        return (await self._get(path))["content"].encode()

    async def import_content(self, path, raw, token, *, format, language="", overwrite=False):
        try:
            old = await self.store.get("fake_asset", digest(path))
        except WorkError:
            old = None
        if old and old["state"] == "present" and not overwrite:
            raise WorkError("Name already exists.")
        row = {
            "id": digest(path),
            "sessionId": "",
            "owner": "local-fixture",
            "asset": {"kind": "file", "id": path},
            "path": path,
            "objectId": old["objectId"] if old and old["state"] == "present" else uuid4().hex,
            "kind": "notebook" if format == "SOURCE" else "file",
            "language": language,
            "content": raw.decode(),
            "modifiedAt": int(time.time() * 1000) + (old["version"] if old else 0),
            "createdAt": old["createdAt"] if old else time.time(),
            "state": "present",
        }
        return await self.store.put("fake_asset", row, old["version"] if old else None)

    async def mkdirs(self, path, token):
        return None

    async def list_dir(self, path, token):
        page = await self.store.page("fake_asset", limit=100)
        return [
            DemoNode(r["path"], r["path"].rsplit("/", 1)[-1], r["kind"])
            for r in page["items"]
            if r["state"] == "present" and r["path"].rsplit("/", 1)[0] == path.rstrip("/")
        ]

    async def search(self, root, query, token):
        page = await self.store.page("fake_asset", limit=100)
        nodes = [
            DemoNode(r["path"], r["path"].rsplit("/", 1)[-1], r["kind"])
            for r in page["items"]
            if r["state"] == "present"
            and r["path"].startswith(root.rstrip("/") + "/")
            and query.casefold() in r["path"].casefold()
        ]
        return nodes, not bool(page["nextCursor"])

    async def remove(self, path, token, *, recursive):
        row = await self._get(path)
        await self.store.put("fake_asset", {**row, "state": "deleted", "content": ""}, row["version"])
