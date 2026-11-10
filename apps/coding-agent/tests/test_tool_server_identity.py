"""The tool server must speak `/api/2.0/postgres` as the APP'S SERVICE PRINCIPAL, always.

Why this file exists, and why it is separate from `test_lakebase_tools.py`.

Spec 013 `[RB-10]` established one platform rule: `postgres` is "always bound to the SP, not OBO",
so a forwarded *user* token never carries it and every Lakebase call answers 403 no matter how many
scopes the app declares or how many times the user signs in. The UI adapters were moved to the
service principal and the tool server was moved only *partly*.

Measured on the deployed app (commit `47ade33`), from a live session:

    dbx_lakebase_status('coding-agent-llm')      -> 403 permission denied
    dbx_lakebase_status('coding-agent-llm-dev')  -> 403 permission denied
    the same GET with the same person's PAT      -> 200 (the project) and 404 (the guessed id)

A 403 for *both* ids can only mean the request carried an identity that may not call the API at all,
because the real id is readable by that very user and the fake id answers 404 — not 403 — to a fresh
credential. So the defect is not the id; it is that these tools presented the user token.

Each test below fails on that tree and passes once the tool server has one identity rule.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

SERVER = Path(__file__).resolve().parents[1] / "tools" / "databricks_notebook_mcp.py"


def load(monkeypatch, *, sp_token: str | None = "sp-token", user_token: str = "user-token"):
    """Load the tool server with a user token AND, when given, a service-principal token.

    The two files are what the orchestrator writes beside each other (`services/orchestrator.py`,
    `_write_token`); a missing `sp_token` is the laptop case.
    """
    monkeypatch.setenv("DATABRICKS_HOST", "https://example.invalid")
    monkeypatch.setenv("DATABRICKS_TOKEN", user_token)
    monkeypatch.setenv("NBMCP_ALLOW_WRITES", "1")
    for key in ("NBMCP_TOKEN_FILE", "NBMCP_SP_TOKEN_FILE"):
        monkeypatch.delenv(key, raising=False)
    if sp_token is not None:
        path = Path(os.environ.get("TMPDIR", "/tmp")) / f"sp-{os.urandom(4).hex()}"
        path.write_text(sp_token)
        monkeypatch.setenv("NBMCP_SP_TOKEN_FILE", str(path))
    spec = importlib.util.spec_from_file_location(f"nbmcp_sp_{os.urandom(4).hex()}", SERVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def record_calls(m):
    """Replace the transport with a recorder that returns `{}` for every call.

    The assertion is about WHICH credential a path is called with, so the response is irrelevant and
    no network may be touched.
    """
    calls: list[tuple[str, str, str]] = []          # (verb, path, token)

    class FakeClient:
        def __init__(self, token):
            self._token = token

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, path, params=None):
            calls.append(("GET", path, self._token))
            return _Resp({})

        def post(self, path, json=None):
            calls.append(("POST", path, self._token))
            return _Resp({})

        def patch(self, path, json=None):
            calls.append(("PATCH", path, self._token))
            return _Resp({})

    class _Resp:
        status_code = 200
        headers = {"content-type": "application/json"}
        text = "{}"
        is_success = True

        def __init__(self, data):
            self._data = data

        def json(self):
            return self._data

        def raise_for_status(self):
            return None

    m._client = lambda: FakeClient(m._token())
    m._sp_client = lambda: FakeClient(m._sp_token())
    m._retry = lambda fn, *, idempotent: fn()
    return calls


def test_a_postgres_read_uses_the_service_principal_not_the_user(monkeypatch):
    """[RB-10] The read that 403'd on the deployed app. A user token can never call this API."""
    m = load(monkeypatch)
    calls = record_calls(m)
    m.dbx_lakebase_list()
    assert calls, "dbx_lakebase_list made no call at all"
    assert {tok for _, _, tok in calls} == {"sp-token"}, \
        f"a Postgres call used the wrong identity: {calls}"


def test_the_endpoint_read_used_by_a_connection_uses_the_service_principal(monkeypatch):
    """`_lakebase_connect` reads the endpoint for its host. It used `_get`, i.e. the user token.

    This is the subtle half of [RB-10]: the tool would pass a permission check on the *management*
    calls and then fail at connect time with an unrelated-looking error, because the host lookup had
    already 403'd.
    """
    m = load(monkeypatch)
    calls = record_calls(m)
    with pytest.raises(RuntimeError, match="no host"):
        m._lakebase_connect("projects/p/branches/b/endpoints/primary", "databricks_postgres", "u")
    assert calls and {tok for _, _, tok in calls} == {"sp-token"}, \
        f"the endpoint read used the wrong identity: {calls}"


def test_the_compute_tool_uses_the_service_principal_for_read_and_write(monkeypatch):
    """A range change was a PATCH on the user token, so it 403'd while the page showed the old range."""
    m = load(monkeypatch)
    calls = record_calls(m)
    m.dbx_lakebase_compute("p", "production", "primary", min_cu=1, max_cu=4)
    assert calls, "dbx_lakebase_compute made no call"
    assert {tok for _, _, tok in calls} == {"sp-token"}, \
        f"dbx_lakebase_compute used the wrong identity: {calls}"
    assert any(v == "PATCH" for v, _, _ in calls), "the range change never reached the API"


def test_without_a_service_principal_the_user_token_is_still_used(monkeypatch):
    """A laptop has no SP. Falling back is the documented behaviour, not a defect."""
    m = load(monkeypatch, sp_token=None)
    calls = record_calls(m)
    m.dbx_lakebase_list()
    assert {tok for _, _, tok in calls} == {"user-token"}


def test_a_role_name_is_never_the_apps_own_client_id_when_the_human_has_a_role(monkeypatch):
    """[RB-11] The username lives on a ROLE, and connecting as the wrong one reads another's objects.

    The tool server picked `role[0]`, so a branch with the app's SP and the user could connect as the
    SP while reporting the user's identity in the answer. It must prefer `DATABRICKS_CLIENT_ID`, the
    same rule `adapters/databricks/lakebase.py::_connect_role` already implements.
    """
    monkeypatch.setenv("DATABRICKS_CLIENT_ID", "sp-client-id")
    m = load(monkeypatch)
    roles = {"roles": [
        {"name": "r1", "status": {"postgres_role": "a-human@example.com"}},
        {"name": "r2", "status": {"postgres_role": "sp-client-id"}},
    ]}
    m._get_sp = lambda path, params=None: roles
    assert m._lakebase_connect_user("p", "production", "a-human@example.com") == "sp-client-id"


def test_a_multi_role_branch_without_the_sp_role_refuses_instead_of_guessing(monkeypatch):
    """Guessing is how a page shows one identity's objects under another's name."""
    monkeypatch.setenv("DATABRICKS_CLIENT_ID", "sp-client-id")
    m = load(monkeypatch)
    m._get_sp = lambda path, params=None: {"roles": [
        {"name": "r1", "status": {"postgres_role": "alice@example.com"}},
        {"name": "r2", "status": {"postgres_role": "bob@example.com"}},
    ]}
    with pytest.raises(RuntimeError, match="minted"):
        m._lakebase_connect_user("p", "production", "carol@example.com")


# -- the refusal's words ------------------------------------------------------------------------
class _FakeRequest:
    def __init__(self, path, method="GET"):
        self.url = type("U", (), {"path": path})()
        self.method = method


class _FakeResponse:
    def __init__(self, path, status=403):
        self.status_code = status
        self.request = _FakeRequest(path)


def test_a_refusal_that_used_the_user_token_says_it_is_a_defect_not_a_grant(monkeypatch):
    """The live confusion, in one assertion.

    With no SP token the tool server falls back to the user token; a 403 then reported "the signed-in
    user or this app's authorization does not allow it", which reads as *ask for a grant* and sent the
    caller to sign in again — a remedy that could never work ([RB-10]).
    """
    m = load(monkeypatch, sp_token=None)
    with pytest.raises(PermissionError) as caught:
        m._refuse_response(_FakeResponse("/api/2.0/postgres/projects/whatever"))
    text = str(caught.value)
    assert "defect in this tool server" in text
    assert "user token" in text
    assert "retry" in text.lower()


def test_a_refusal_that_used_the_sp_token_names_the_service_principal(monkeypatch):
    m = load(monkeypatch)
    with pytest.raises(PermissionError) as caught:
        m._refuse_response(_FakeResponse("/api/2.0/postgres/projects/whatever"))
    text = str(caught.value)
    assert "service principal" in text
    assert "defect in this tool server" not in text


def test_no_postgres_call_can_use_the_user_transport():
    """A structural guard, because a call site is what got this wrong twice.

    Every `_get`/`_post`/`_patch` whose path starts with the Postgres base must be the `_sp` variant.
    This reads the source instead of running it, which is the only way to assert a property of ALL
    call sites — including the ones a future change adds.
    """
    import re

    text = SERVER.read_text()
    # A call whose first argument is a Postgres path, written on one line in this file.
    bad = re.findall(r"\b(_get|_post|_patch)\(\s*f?[\"']/api/2\.0/postgres", text)
    assert not bad, (
        f"{len(bad)} Postgres call(s) use the user-token transport {bad}; they must be "
        "_get_sp/_post_sp/_patch_sp, because that API cannot be called with a user token ([RB-10])"
    )

