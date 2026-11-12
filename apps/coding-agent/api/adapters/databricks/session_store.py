"""The session store on a Unity Catalog volume, through the Files API. The only code that reaches it.

A session's commands and results are small JSON files. They are written whole (the Files API replaces a
file in one request, so a reader never sees half of one) and read back by path. A file that is not there
is `None`, not an error: "not yet" is the normal answer to most polls.

The app's own identity does this (the same service principal that runs the session), so the principal
needs read and write on the volume. Without that the first write fails and the caller says so.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
from typing import Any

log = logging.getLogger(__name__)


class VolumeStore:
    def __init__(self, client: Any | None = None) -> None:
        self._client = client

    def _w(self) -> Any:
        if self._client is None:
            from databricks.sdk import WorkspaceClient  # imported late: a demo needs no SDK auth

            self._client = WorkspaceClient()
        return self._client

    async def put(self, path: str, doc: dict[str, Any]) -> None:
        await asyncio.to_thread(self._put, path, doc)

    def _put(self, path: str, doc: dict[str, Any]) -> None:
        self._w().files.upload(path, io.BytesIO(json.dumps(doc).encode("utf-8")), overwrite=True)

    async def get(self, path: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get, path)

    def _get(self, path: str) -> dict[str, Any] | None:
        from databricks.sdk.errors import NotFound

        try:
            data = self._w().files.download(path).contents.read()
        except NotFound:
            return None
        try:
            doc = json.loads(data)
        except ValueError:
            return None          # being replaced as we read it, or not ours: the next poll decides
        return doc if isinstance(doc, dict) else None

    async def delete_tree(self, root: str) -> None:
        await asyncio.to_thread(self._delete_tree, root)

    def _delete_tree(self, root: str) -> None:
        from databricks.sdk.errors import NotFound

        w = self._w()

        def walk(directory: str) -> None:
            try:
                entries = list(w.files.list_directory_contents(directory))
            except NotFound:
                return
            for e in entries:
                if e.is_directory:
                    walk(e.path)
                else:
                    w.files.delete(e.path)
            w.files.delete_directory(directory)

        try:
            walk(root.rstrip("/"))
        except Exception as exc:  # noqa: BLE001 - scratch files left behind are not worth an error
            log.debug("could not remove %s: %s", root, exc)
