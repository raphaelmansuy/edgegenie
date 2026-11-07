"""Workspace tree: the endpoint contract and the failure modes that matter."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from test_api import make_client  # noqa: E402  (same fixtures, one place)


class FakeBrowser:
    """Stands in for the workspace API so the endpoint can be tested without a workspace."""

    def __init__(self, folders: dict[str, list[dict]], deny: set[str] | None = None) -> None:
        self.folders = folders          # not `tree`: that would shadow the tree() method below
        self.deny = deny or set()

    async def list_dir(self, path: str, token: str | None):
        from api.adapters.databricks.workspace import KIND, Node
        if path in self.deny:
            raise PermissionError(f"you do not have access to {path}")
        rows = self.folders.get(path, [])
        nodes = [Node(path=r["path"], name=r["path"].rsplit("/", 1)[-1],
                      kind=KIND.get(r["type"], "file"), language=r.get("language", ""),
                      has_children=r["type"] in ("DIRECTORY", "REPO")) for r in rows]
        nodes.sort(key=lambda n: (n.kind not in ("directory", "repo"), n.name.lower()))
        return nodes

    async def tree(self, path: str, token: str | None, depth: int = 1):
        from api.adapters.databricks.workspace import Node
        root = Node(path=path, name=path.rsplit("/", 1)[-1], kind="directory", has_children=True)
        root.children = await self.list_dir(path, token)
        if depth > 1:
            for child in root.children:
                if child.has_children:
                    child.children = await self.list_dir(child.path, token)
        return root


@pytest.fixture
def client_with_tree():
    c = make_client()
    # NOTE: TestClient exposes the FastAPI app on .app, and state.workspace is shadowed by the
    # real browser until we reassign it here. Keep this assignment first, before any request.
    c.app.state.workspace = FakeBrowser({
        "/Users/tester@example.com": [
            {"path": "/Users/tester@example.com/notebook_a", "type": "NOTEBOOK", "language": "PYTHON"},
            {"path": "/Users/tester@example.com/sub", "type": "DIRECTORY"},
            {"path": "/Users/tester@example.com/data.csv", "type": "FILE"},
        ],
        "/Users/tester@example.com/sub": [
            {"path": "/Users/tester@example.com/sub/inner", "type": "NOTEBOOK", "language": "SQL"},
        ],
    })
    return c


def test_lists_a_folder_folders_first(client_with_tree):
    d = client_with_tree.get("/api/workspace?path=/Users/tester@example.com").json()
    kinds = [c["kind"] for c in d["node"]["children"]]
    assert kinds[0] == "directory", "folders must come first"
    assert kinds[1:] == ["file", "notebook"] or "notebook" in kinds


def test_a_notebook_reports_its_language(client_with_tree):
    kids = client_with_tree.get("/api/workspace?path=/Users/tester@example.com").json()["node"]["children"]
    nb = next(c for c in kids if c["kind"] == "notebook")
    assert nb["language"] == "PYTHON"
    assert nb["hasChildren"] is False, "a notebook is a leaf"


def test_the_tree_is_lazy_a_folder_is_not_expanded_by_default(client_with_tree):
    kids = client_with_tree.get("/api/workspace?path=/Users/tester@example.com").json()["node"]["children"]
    folder = next(c for c in kids if c["kind"] == "directory")
    assert folder["hasChildren"] is True
    assert "children" not in folder, "children load when the user opens the folder"


def test_depth_two_expands_one_level(client_with_tree):
    d = client_with_tree.get("/api/workspace?path=/Users/tester@example.com&depth=2").json()
    folder = next(c for c in d["node"]["children"] if c["kind"] == "directory")
    assert folder["children"][0]["name"] == "inner"


def test_an_unreadable_folder_is_a_403_not_an_empty_list(client_with_tree):
    client_with_tree.app.state.workspace = FakeBrowser({}, deny={"/Users/tester@example.com"})
    r = client_with_tree.get("/api/workspace?path=/Users/tester@example.com")
    assert r.status_code == 403
    assert "do not have access" in r.json()["detail"]


def test_roots_only_include_places_that_exist(client_with_tree):
    roots = client_with_tree.get("/api/workspace/roots").json()["roots"]
    paths = [r["path"] for r in roots]
    assert "/Users/tester@example.com" in paths
    assert "/Shared" not in paths, "a root that opens onto nothing must not be offered"


def test_the_token_is_never_returned(client_with_tree):
    r = client_with_tree.get("/api/workspace?path=/Users/tester@example.com",
                             headers={"x-forwarded-access-token": "dapi1234567890abcdef"})
    assert "dapi" not in r.text


# -- a missing OAuth scope is the app's problem, and the sentence says so ---------------------
def test_a_missing_scope_is_reported_as_an_app_setting_not_as_the_users_access():
    from api.adapters.databricks.http import ScopeMissing, denial

    err = denial(403, '{"message":"Provided OAuth token does not have required scopes: workspace"}', "/")
    assert isinstance(err, ScopeMissing) and isinstance(err, PermissionError)
    assert err.scopes == "workspace"
    assert "app setting" in str(err) and "not your access" in str(err)
    assert "you do not have access" not in str(err)


def test_an_acl_denial_still_names_the_path():
    from api.adapters.databricks.http import ScopeMissing, denial

    err = denial(403, '{"error_code":"PERMISSION_DENIED","message":"User does not have READ on /Shared/x"}', "/Shared/x")
    assert not isinstance(err, ScopeMissing)
    assert str(err) == "you do not have access to /Shared/x"


def test_the_platforms_actual_scope_refusal_is_recognised_and_names_the_scope():
    """The verbatim bodies from the deployed app's log (2026-11-07): no 'token', no 'oauth'."""
    from api.adapters.databricks.http import ScopeMissing, denial

    ws = denial(403, "Invalid scope, required scopes: workspace", "/")
    uc = denial(403, "Invalid scope, required scopes: unity-catalog", "/api/2.1/unity-catalog/catalogs")
    assert isinstance(ws, ScopeMissing) and ws.scopes == "workspace"
    assert isinstance(uc, ScopeMissing) and uc.scopes == "unity-catalog"
    assert "`unity-catalog`" in str(uc)


def test_token_scopes_reads_names_only():
    import base64, json
    from api.domain.redact import token_scopes

    def jwt(claims):
        enc = lambda o: base64.urlsafe_b64encode(json.dumps(o).encode()).rstrip(b"=").decode()
        return f"{enc({'alg': 'none'})}.{enc(claims)}.sig"

    assert token_scopes(jwt({"scope": "sql files workspace", "sub": "x"})) == ["files", "sql", "workspace"]
    assert token_scopes(jwt({"scp": ["b", "a"]})) == ["a", "b"]
    assert token_scopes(jwt({})) == []
    assert token_scopes("dapi-opaque-token") == []      # not a JWT: nothing readable, nothing raised
    assert token_scopes(None) == [] and token_scopes("a.!!!.c") == []
