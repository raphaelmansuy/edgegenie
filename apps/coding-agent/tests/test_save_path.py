"""The fenced write path: spec 003 WR-1..WR-7 and CX-2.

The test that matters most is `test_save_obeys_check_path_when_it_is_mutated`: every other test here
could pass with a route that re-implements the fence and happens to agree with it. That one flips
`check_path` to always-deny and requires the route to refuse — so it fails if the route has its own
policy instead of calling the shared one.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from api.domain import approval, scope as scope_mod  # noqa: E402
from test_api import make_client  # noqa: E402  (one place for the fixtures)
from test_workspace import FakeBrowser  # noqa: E402

HOME = "/Users/tester@example.com"
SCRATCH = f"{HOME}/agent_scratch"


class SaveBrowser(FakeBrowser):
    """A workspace that remembers what was imported, and can report a version."""

    def __init__(self, files: dict[str, str] | None = None, modified: int = 1_700_000_000):
        super().__init__({})
        self.files = dict(files or {})
        self.modified = modified
        self.imports: list[tuple[str, str]] = []

    async def status(self, path: str, token: str | None) -> dict:
        if path not in self.files:
            raise LookupError(f"{path} does not exist")
        return {"object_id": f"oid-{abs(hash(path)) % 10**8}", "modified_at": self.modified,
                "size": len(self.files[path].encode()), "language": "PYTHON",
                "object_type": "NOTEBOOK"}

    async def import_source(self, path: str, text: str, token: str | None, *, language: str = "",
                            overwrite: bool = True) -> dict:
        if path in self.files and not overwrite:
            raise RuntimeError("already exists")
        self.files[path] = text
        self.modified += 1
        self.imports.append((path, text))
        return {"path": path}


@pytest.fixture
def save_client():
    c = make_client()
    c.app.state.workspace = SaveBrowser()
    # A session whose folder is agent_scratch, so the fence has something to be inside of.
    body = c.post("/api/sessions", json={"folder": SCRATCH, "model": "fake/model-a"}).json()
    c.session_id = body["id"]
    return c


def save(client, path, text, version=None, approval_token=None, session=True, language=None):
    return client.post("/api/workspace/save", json={
        "path": path, "text": text, "version": version, "approval": approval_token,
        "language": language,
        "sessionId": client.session_id if session else None,
    })


# ---------------------------------------------------------------- the fence
def test_create_inside_the_fence_needs_no_approval(save_client):
    r = save(save_client, f"{SCRATCH}/notes.py", "print(1)\n", version="")
    assert r.status_code == 200, r.text
    assert save_client.app.state.workspace.files[f"{SCRATCH}/notes.py"] == "print(1)\n"
    assert r.json()["fence"] == "allow"


def test_save_outside_the_fence_is_refused_without_an_approval(save_client):
    r = save(save_client, "/Shared/someone_elses.py", "x\n", version="")
    assert r.status_code == 403
    detail = r.json()["detail"]
    assert detail["fence"] == "ask"
    assert SCRATCH in detail["reason"]
    assert save_client.app.state.workspace.imports == []


def test_save_outside_the_fence_succeeds_with_an_approval(save_client):
    path = "/Shared/team_notes.py"
    fence = save_client.post("/api/workspace/fence", json={"path": path, "version": "", "sessionId": save_client.session_id}).json()
    assert fence["verdict"] == "ask"
    r = save(save_client, path, "x = 1\n", version="", approval_token=fence["approval"])
    assert r.status_code == 200, r.text
    assert save_client.app.state.workspace.files[path] == "x = 1\n"


def test_an_approval_for_one_path_cannot_authorise_another(save_client):
    """WR-3: the approval names a path. Reusing it elsewhere is the whole attack."""
    a = save_client.post("/api/workspace/fence", json={"path": "/Shared/a.py", "version": "", "sessionId": save_client.session_id}).json()
    r = save(save_client, "/Shared/b.py", "x\n", version="", approval_token=a["approval"])
    assert r.status_code == 403
    assert "/Shared/b.py" not in save_client.app.state.workspace.files


def test_an_expired_approval_is_refused():
    """The token is time-bound; an approval is a decision about now."""
    path, ver = "/Shared/x.py", ""
    token = approval.issue(path, ver, now=1_000_000, ttl=60)
    assert approval.verify(token, path, ver, now=1_000_030) is True
    assert approval.verify(token, path, ver, now=1_000_100) is False


def test_a_forged_approval_is_refused():
    assert approval.verify("9999999999.deadbeef", "/Shared/x.py", "") is False
    assert approval.verify("not-a-token", "/Shared/x.py", "") is False
    assert approval.verify(None, "/Shared/x.py", "") is False


def test_rejects_a_traversal_path(save_client):
    """A7: `..` must never be silently allowed, whatever the fence says elsewhere."""
    r = save(save_client, f"{SCRATCH}/../etc/passwd", "x\n", version="")
    assert r.status_code == 422
    assert save_client.app.state.workspace.imports == []


# ---------------------------------------------------------------- the mutation test (WR-1)
def test_save_obeys_check_path_when_it_is_mutated(save_client, monkeypatch):
    """The route must call `check_path`, not re-implement it.

    Flip the shared function to always deny. A route that consults it must refuse an in-fence save
    that it just allowed a moment ago. A route with its own policy would still succeed, and this
    test — the only one that can see the difference — would fail.
    """
    ok = save(save_client, f"{SCRATCH}/before.py", "x\n", version="")
    assert ok.status_code == 200

    monkeypatch.setattr(scope_mod, "check_path",
                        lambda scope, path: scope_mod.Decision(scope_mod.Verdict.DENY, scope_mod.Action.WRITE,
                                                               path, "mutated: deny everything"))
    after = save(save_client, f"{SCRATCH}/after.py", "y\n", version="")
    assert after.status_code == 403
    assert "mutated" in str(after.json()["detail"])
    assert f"{SCRATCH}/after.py" not in save_client.app.state.workspace.files


# ---------------------------------------------------------------- versions (CX-2)
def test_create_then_update_with_the_returned_version(save_client):
    path = f"{SCRATCH}/a.py"
    created = save(save_client, path, "v1\n", version="")
    v1 = created.json()["version"]["token"]
    updated = save(save_client, path, "v2\n", version=v1)
    assert updated.status_code == 200, updated.text
    assert save_client.app.state.workspace.files[path] == "v2\n"


def test_a_stale_version_is_a_conflict_not_an_overwrite(save_client):
    path = f"{SCRATCH}/b.py"
    v1 = save(save_client, path, "v1\n", version="").json()["version"]["token"]
    # Somebody else writes.
    save_client.app.state.workspace.files[path] = "theirs\n"
    save_client.app.state.workspace.modified += 10
    # We still hold v1.
    r = save(save_client, path, "mine\n", version=v1)
    assert r.status_code == 409
    body = r.json()["detail"]
    assert body["conflict"] is True
    assert body["yours"] == v1
    assert body["current"]["token"] != v1
    assert save_client.app.state.workspace.files[path] == "theirs\n"


def test_overwriting_without_a_version_is_a_conflict(save_client):
    """CX-2: a write with no version onto an existing object is the silent clobber we forbid."""
    path = f"{SCRATCH}/c.py"
    save(save_client, path, "v1\n", version="")
    r = save(save_client, path, "clobber\n", version=None)
    assert r.status_code == 409
    assert r.json()["detail"]["reason"].startswith("no version supplied")
    assert save_client.app.state.workspace.files[path] == "v1\n"


def test_conflict_carries_both_versions(save_client):
    path = f"{SCRATCH}/d.py"
    v1 = save(save_client, path, "a\n", version="").json()["version"]["token"]
    save_client.app.state.workspace.files[path] = "b\n"
    save_client.app.state.workspace.modified += 5
    detail = save(save_client, path, "c\n", version=v1).json()["detail"]
    assert set(detail) >= {"conflict", "current", "yours", "path"}
    assert detail["path"] == path


# ---------------------------------------------------------------- the fence preview (WR-5)
def test_fence_endpoint_explains_before_writing(save_client):
    inside = save_client.post("/api/workspace/fence", json={"path": f"{SCRATCH}/x.py", "sessionId": save_client.session_id}).json()
    assert inside["verdict"] == "allow"
    assert inside["approval"] is None
    outside = save_client.post("/api/workspace/fence", json={"path": "/Shared/x.py", "sessionId": save_client.session_id}).json()
    assert outside["verdict"] == "ask"
    assert outside["approval"]                    # a usable token, not just a verdict
    assert "/Shared/x.py" in outside["target"] or outside["target"]


def test_fence_never_writes(save_client):
    before = dict(save_client.app.state.workspace.files)
    save_client.post("/api/workspace/fence", json={"path": f"{SCRATCH}/phantom.py", "sessionId": save_client.session_id})
    assert save_client.app.state.workspace.files == before


# ---------------------------------------------------------------- the audit (WR-4)
def _events(client, session_id):
    """Read the recorded events without opening the SSE stream.

    `GET /api/sessions/{id}/stream` is an infinite generator by design (it is a live feed), so a
    test that reads it whole hangs forever. The store is the honest place to look for "was this
    recorded".
    """
    import asyncio

    store = client.app.state.store
    return asyncio.run(store.since(session_id, 0))


def test_a_save_is_recorded_in_the_session_stream(save_client):
    path = f"{SCRATCH}/audited.py"
    save(save_client, path, "x = 1\n", version="")
    rows = _events(save_client, save_client.session_id)
    kinds = [r["type"] for r in rows]
    assert "document.saved" in kinds, kinds
    saved = next(r for r in rows if r["type"] == "document.saved")
    assert saved["path"] == path
    assert saved["by"] == "human"
    assert saved["size"] == len("x = 1\n".encode())


def test_a_save_without_a_session_still_works(save_client):
    """An editor open with no session must not be a dead end; it simply always asks."""
    r = save(save_client, "/Shared/no_session.py", "x\n", version="", session=False)
    assert r.status_code == 403            # no scope => outside => asks
    fence = save_client.post("/api/workspace/fence", json={"path": "/Shared/no_session.py"}).json()
    r2 = save(save_client, "/Shared/no_session.py", "x\n", version="",
              approval_token=fence["approval"], session=False)
    assert r2.status_code == 200, r2.text


def test_save_reports_the_size_it_wrote(save_client):
    body = save(save_client, f"{SCRATCH}/size.py", "héllo\n", version="").json()
    assert body["size"] == len("héllo\n".encode("utf-8"))     # bytes, not characters


# ---------------------------------------------------------------- the fence cannot be widened by accident
def test_an_empty_folder_is_not_a_wildcard():
    """A session-less scope must not allow everything.

    `"anything".startswith("")` is True, so a literal prefix test on an empty folder classifies
    every path as inside the fence and silently permits the write. That bug was introduced while
    making the no-session message human-readable, and caught by
    `test_a_save_without_a_session_still_works`. This test states the property directly so the
    next person cannot reintroduce it.
    """
    from api.domain import scope as scope_mod

    empty = scope_mod.Scope.for_session("x", "", None)
    for path in ["/Users/anyone/agent_scratch/a.py", "/Shared/b.py", "/etc/passwd", "/a"]:
        assert scope_mod.check_path(empty, path).verdict is scope_mod.Verdict.ASK, path
    assert "no session" in scope_mod.check_path(empty, "/a").reason


def test_a_root_folder_is_not_a_wildcard():
    """`/` as a folder would also match everything; treat it as "no fence", not "all of it"."""
    from api.domain import scope as scope_mod

    root = scope_mod.Scope.for_session("x", "/", None)
    assert scope_mod.check_path(root, "/Users/anyone/x.py").verdict is scope_mod.Verdict.ASK


def test_a_normal_folder_still_allows_what_is_inside_it():
    """The guard must not break the case it exists to protect."""
    from api.domain import scope as scope_mod

    s = scope_mod.Scope.for_session("x", "/Users/me/agent_scratch/", None)
    assert scope_mod.check_path(s, "/Users/me/agent_scratch/a.py").verdict is scope_mod.Verdict.ALLOW
    assert scope_mod.check_path(s, "/Users/me/other/a.py").verdict is scope_mod.Verdict.ASK
