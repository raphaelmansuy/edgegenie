"""Right-click workspace actions: what is refused, and the order a copy-then-trash must keep.

The order is the safety property. The original is deleted only after the destination exists, and a
failed copy of a folder removes the partial destination instead of leaving both trees half-done.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from test_api import make_client  # noqa: E402

from api.adapters.databricks.workspace import WorkspaceBrowser
from api.domain.workspace_ops import clean_name, is_protected


def test_roots_and_the_users_home_are_protected_and_their_children_are_not():
    home = "/Users/tester@example.com"
    assert is_protected("/Users", home)
    assert is_protected("/Shared", home)
    assert is_protected("/Repos", home)
    assert is_protected(home, home)
    assert is_protected("/Repos/tester", home)
    assert not is_protected(f"{home}/agent_scratch", home)
    assert not is_protected("/Shared/e2e_outside_fence", home)
    assert not is_protected("/Repos/tester/edgedata", home)


def test_a_name_is_one_segment():
    assert clean_name("  notes.py ") == "notes.py"
    for bad in ("", ".", "..", "a/b", "a\\b", "a\x00b", "x" * 201):
        with pytest.raises(ValueError):
            clean_name(bad)


class Store:
    """Just enough of the workspace API to watch the order of calls."""

    def __init__(self):
        self.objects: dict[str, dict] = {}
        self.calls: list[str] = []
        self.fail_import = False

    async def get(self, path, token, params=None):  # noqa: ARG002
        self.calls.append(path.rsplit("/", 1)[-1])
        p = (params or {}).get("path", "")
        if path.endswith("/get-status"):
            if p not in self.objects:
                raise LookupError(p)
            return self.objects[p]
        if path.endswith("/export"):
            obj = self.objects[p]
            return {"content": base64.b64encode(obj["raw"]).decode()}
        if path.endswith("/list"):
            prefix = p.rstrip("/") + "/"
            children = []
            for full, obj in self.objects.items():
                if full.startswith(prefix) and "/" not in full[len(prefix):]:
                    children.append({"path": full, "object_type": obj["object_type"], "language": obj.get("language", "")})
            return {"objects": children}
        raise AssertionError(path)

    async def post(self, path, token, body=None):  # noqa: ARG002
        body = body or {}
        self.calls.append(path.rsplit("/", 1)[-1])
        if path.endswith("/mkdirs"):
            self.objects[body["path"]] = {"object_type": "DIRECTORY", "raw": b"", "object_id": "d"}
            return {}
        if path.endswith("/import"):
            if self.fail_import:
                raise RuntimeError("import refused")
            self.objects[body["path"]] = {
                "object_type": "NOTEBOOK" if body.get("language") else "FILE",
                "language": body.get("language", ""),
                "raw": base64.b64decode(body["content"]),
                "object_id": "n",
            }
            return {}
        if path.endswith("/delete"):
            target = body["path"]
            if body.get("recursive"):
                self.objects = {k: v for k, v in self.objects.items() if k != target and not k.startswith(target + "/")}
            else:
                self.objects.pop(target, None)
            return {}
        raise AssertionError(path)


def browser(store: Store) -> WorkspaceBrowser:
    return WorkspaceBrowser("https://example", lambda: None, store)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_a_move_copies_before_it_deletes_and_a_clone_keeps_the_original():
    store = Store()
    store.objects["/Users/a/notes"] = {"object_type": "NOTEBOOK", "language": "SQL", "raw": b"select 1", "object_id": "1"}
    await browser(store).relocate("/Users/a/notes", "/Users/a/notes-2", None, move=True)
    assert store.calls.index("export") < store.calls.index("import") < store.calls.index("delete")
    assert store.objects["/Users/a/notes-2"]["raw"] == b"select 1"
    assert store.objects["/Users/a/notes-2"]["language"] == "SQL"
    assert "/Users/a/notes" not in store.objects

    store.calls.clear()
    await browser(store).relocate("/Users/a/notes-2", "/Users/a/notes-3", None, move=False)
    assert "delete" not in store.calls
    assert "/Users/a/notes-2" in store.objects and "/Users/a/notes-3" in store.objects


@pytest.mark.asyncio
async def test_an_existing_destination_is_refused_before_anything_is_read():
    store = Store()
    store.objects["/Users/a/notes"] = {"object_type": "FILE", "raw": b"x", "object_id": "1"}
    store.objects["/Users/a/taken"] = {"object_type": "FILE", "raw": b"y", "object_id": "2"}
    with pytest.raises(FileExistsError):
        await browser(store).relocate("/Users/a/notes", "/Users/a/taken", None, move=True)
    assert "export" not in store.calls and "delete" not in store.calls
    assert store.objects["/Users/a/notes"]["raw"] == b"x"


@pytest.mark.asyncio
async def test_a_failed_folder_copy_removes_the_partial_and_keeps_the_original():
    store = Store()
    store.objects["/Users/a/proj"] = {"object_type": "DIRECTORY", "raw": b"", "object_id": "d"}
    store.objects["/Users/a/proj/n"] = {"object_type": "NOTEBOOK", "language": "PYTHON", "raw": b"print(1)", "object_id": "n"}
    store.fail_import = True
    with pytest.raises(RuntimeError, match="import refused"):
        await browser(store).relocate("/Users/a/proj", "/Users/a/proj-2", None, move=True)
    assert "/Users/a/proj/n" in store.objects
    assert "/Users/a/proj-2" not in store.objects


@pytest.mark.asyncio
async def test_a_git_folder_is_not_copied():
    store = Store()
    store.objects["/Repos/a/demo"] = {"object_type": "REPO", "raw": b"", "object_id": "r"}
    with pytest.raises(ValueError, match="Git folder"):
        await browser(store).relocate("/Repos/a/demo", "/Repos/a/demo-2", None, move=True)
    assert "mkdirs" not in store.calls and "delete" not in store.calls


class OpsWs:
    def __init__(self):
        self.deleted = None
        self.transferred = None
        self.created = None

    async def exists(self, path, token):  # noqa: ARG002
        return path.endswith("/taken")

    async def mkdirs(self, path, token):  # noqa: ARG002
        self.created = ("folder", path)

    async def import_content(self, path, raw, token, *, format, language=""):  # noqa: ARG002
        self.created = (format, language, path, raw)

    async def remove(self, path, token, *, recursive):  # noqa: ARG002
        self.deleted = (path, recursive)

    async def relocate(self, source, dest, token, *, move):  # noqa: ARG002
        self.transferred = (source, dest, move)

    async def export_content(self, path, token, format):  # noqa: ARG002
        return b"hello"

    async def permissions(self, path, token):  # noqa: ARG002
        return [{"who": "users", "principal": "group", "permission": "CAN_READ", "inherited": True}]


def test_the_routes_refuse_a_root_and_carry_out_the_rest():
    with make_client() as client:
        ws = OpsWs()
        client.app.state.workspace = ws
        home = "/Users/tester@example.com"
        assert client.post("/api/workspace/delete", json={"path": home}).status_code == 422
        assert client.post("/api/workspace/delete", json={"path": "/Repos/tester", "recursive": True}).status_code == 422
        assert client.post("/api/workspace/delete", json={"path": f"{home}/proj", "recursive": True}).status_code == 200
        assert ws.deleted == (f"{home}/proj", True)

        made = client.post("/api/workspace/object", json={"parent": home, "name": "n", "kind": "notebook", "language": "SQL"})
        assert made.status_code == 201, made.text
        assert ws.created[:3] == ("SOURCE", "SQL", f"{home}/n")
        assert client.post("/api/workspace/object", json={"parent": home, "name": "a/b", "kind": "file"}).status_code == 422
        assert client.post("/api/workspace/object", json={"parent": home, "name": "taken", "kind": "file"}).status_code == 409

        assert client.post("/api/workspace/transfer", json={
            "source": "/Shared", "destination": f"{home}/x", "mode": "move"}).status_code == 422
        moved = client.post("/api/workspace/transfer", json={
            "source": f"{home}/n", "destination": f"{home}/m", "mode": "copy"})
        assert moved.status_code == 200 and ws.transferred == (f"{home}/n", f"{home}/m", False)

        exported = client.get(f"/api/workspace/export?path={home}/n&format=SOURCE")
        assert exported.status_code == 200 and exported.content == b"hello"
        assert client.get(f"/api/workspace/export?path={home}/n&format=NOPE").status_code == 422
        assert client.get(f"/api/workspace/permissions?path={home}/n").json()["entries"][0]["permission"] == "CAN_READ"
