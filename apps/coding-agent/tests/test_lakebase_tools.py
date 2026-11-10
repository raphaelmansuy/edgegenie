"""The Lakebase rules and the Postgres-API adapters, tested without a workspace.

Two halves:

* `api.domain.lakebase` — pure: identity, the capacity arithmetic, the state words.
* `api.adapters.databricks.lakebase` / `apps` — through a fake HTTP seam, asserting the **method,
  path and body** of every call. That is the test that keeps the Provisioned dialect from creeping
  back (spec 013 [LB-1], [RB-6]): a URL test is crude and exactly right when the defect is a
  vocabulary.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from api.adapters.databricks.apps import AppsBrowser, apps_using, health_word, state_of
from api.adapters.databricks.lakebase import LakebaseBrowser, page_blocks
from api.domain import lakebase as lb

APP = Path(__file__).resolve().parents[1]


# -- identity -----------------------------------------------------------------------------------
def test_a_project_has_one_key_however_it_is_spelled():
    """[LB-5], [E-24] The notebook equivalent is `canonicalPath`; two tabs for one object is the bug."""
    assert lb.project_ref("pg_tickets") == "projects/pg_tickets"
    assert lb.project_ref("projects/pg_tickets") == "projects/pg_tickets"
    assert lb.project_ref("/projects/pg_tickets/") == "projects/pg_tickets"
    assert lb.project_id("projects/pg_tickets") == "pg_tickets"


def test_a_branch_ref_is_built_and_read_back():
    assert lb.branch_ref("pg_tickets", "production") == "projects/pg_tickets/branches/production"
    assert lb.branch_ref("projects/pg_tickets", "agent-9") == "projects/pg_tickets/branches/agent-9"
    assert lb.branch_id("projects/pg_tickets/branches/agent-9") == "agent-9"
    assert lb.branch_id("agent-9") == "agent-9"


def test_an_endpoint_is_what_a_credential_is_minted_for():
    assert (lb.endpoint_ref("pg_tickets", "production")
            == "projects/pg_tickets/branches/production/endpoints/primary")


def test_an_empty_project_is_refused_rather_than_silently_rooted():
    with pytest.raises(lb.LakebaseError):
        lb.project_ref("   ")


# -- the capacity arithmetic --------------------------------------------------------------------
@pytest.mark.parametrize("low,high,zero,valid", [
    (0.5, 16.5, False, True),
    (0.5, 16.51, False, False),
    (48, 64, False, True),
    (8, 24, False, True),          # exactly 16 apart
    (8, 24.1, False, False),
    (0.4, 4, False, False),
    (2, 66, False, False),
    (8, 4, False, False),
    (0.5, 16, True, True),         # scale-to-zero, inside both rules
    (16, 32, True, True),          # exactly 16 apart, at the scale-to-zero ceiling
    (32, 48, True, False),         # spread ok, but above the scale-to-zero ceiling
])
def test_the_autoscaling_rule_is_the_platform_s(low, high, zero, valid):
    """[LB-4], [E-7] max − min ≤ 16, 0.5 ≤ min, max ≤ 64, scale-to-zero only when max ≤ 32.

    The spread rule binds first: `0.5 → 32` is 31.5 apart and illegal before the scale-to-zero rule
    is even consulted, which is why the page shows the arithmetic rather than only a verdict.
    """
    assert lb.Range(low, high, zero).valid is valid


def test_the_spread_rule_binds_before_the_scale_to_zero_rule():
    """Two rules can both be violated; the sentence names the first, so the fix is one edit."""
    problem = lb.Range(0.5, 32, True).problem
    assert "16" in problem and "31.5" in problem
    assert "scale to zero" not in problem


def test_the_range_problem_names_the_number_and_the_fix():
    problem = lb.Range(0.5, 32).problem
    assert "16" in problem and "31.5" in problem and "at most 16.5" in problem


def test_the_range_describes_itself_for_a_page():
    """The string S2 shows: the rule, evaluated, next to the range."""
    text = lb.Range(0.5, 4).describe()
    assert "0.5 – 4 CU" in text and "max − min = 3.5" in text and "✓" in text


def test_a_range_is_read_from_either_shape():
    assert lb.range_from({"spec": {"autoscaling_limit_min_cu": 1, "autoscaling_limit_max_cu": 4}}) == lb.Range(1, 4)
    assert lb.range_from({"status": {"autoscaling_limit_min_cu": 2, "autoscaling_limit_max_cu": 8}}) == lb.Range(2, 8)
    assert lb.range_from({}) == lb.Range(0.5, 0.5)


# -- state words --------------------------------------------------------------------------------
@pytest.mark.parametrize("raw,word", [
    ("READY", "ready"), ("AVAILABLE", "ready"), ("PROVISIONING", "starting"),
    ("SUSPENDED", "asleep"), ("FAILED", "failed"), ("SOMETHING_NEW", "something_new"),
])
def test_a_state_is_translated_or_shown_verbatim(raw, word):
    """An unknown state is returned verbatim: a plausible paraphrase is worse than the platform's word."""
    assert lb.state_word(raw) == word
    assert lb.is_ready(raw) is (word == "ready")


def test_a_suspended_compute_is_a_state_not_a_failure():
    """[RB-7] A connection resumes it; reporting "down" teaches users to distrust the page."""
    assert lb.is_suspended("SUSPENDED") and not lb.is_ready("SUSPENDED")


# -- identifiers ---------------------------------------------------------------------------------
@pytest.mark.parametrize("bad", ['x"; DROP DATABASE y; --', "a'b", "1x", "a b", ""])
def test_an_identifier_that_needs_escaping_is_refused(bad):
    """[E-19] An identifier that needs escaping is not an identifier."""
    assert lb.check_identifier(bad, "database") is not None


# -- the adapter: every URL is the Postgres API --------------------------------------------------
class FakeHttp:
    def __init__(self, routes=None):
        self.routes = routes or {}
        self.calls: list[tuple] = []

    async def get(self, path, token, params=None):
        self.calls.append(("GET", path, params))
        out = self.routes.get(path)
        if isinstance(out, BaseException):
            raise out
        if out is None:
            raise LookupError(f"not found: {path}")
        return out

    async def post(self, path, token, body=None, timeout=0):
        self.calls.append(("POST", path, body))
        out = self.routes.get(path)
        if isinstance(out, BaseException):
            raise out
        return out or {"token": "tok"}


def run(coro):
    return asyncio.run(coro)


def test_the_adapter_never_speaks_the_provisioned_dialect():
    """[LB-1], [RB-6] The defect was a vocabulary, so the test forbids the words.

    A grep over a source file is crude; it is exactly right here, because the old API still answers
    with the old shape and a silent success is the failure mode."""
    source = (APP / "api" / "adapters" / "databricks" / "lakebase.py").read_text()
    for forbidden in ("read_write_dns", "instance_names", "/database/instances", "/database/credentials"):
        assert forbidden not in source, f"the adapter must not use {forbidden!r}"
    assert "/api/2.0/postgres" in source


def test_listing_projects_is_one_call():
    """[06 §6.1] The rail lists them on every load; a per-project call would be a fan-out."""
    http = FakeHttp({"/api/2.0/postgres/projects": {"projects": [
        {"name": "projects/a", "status": {"state": "READY", "display_name": "A"}},
        {"name": "projects/b", "status": {"state": "PROVISIONING"}},
    ]}})
    b = LakebaseBrowser("h", None, http=http)
    rows = run(b.projects("tok"))
    assert [r["name"] for r in rows] == ["a", "b"]
    assert rows[0]["state"] == "ready" and rows[1]["state"] == "starting"
    assert len(http.calls) == 1


def test_a_project_read_carries_its_version_and_default_branch():
    http = FakeHttp({"/api/2.0/postgres/projects/a": {
        "name": "projects/a", "spec": {"pg_version": 17, "default_branch": "projects/a/branches/production"},
        "status": {"state": "READY", "display_name": "Tickets"}}})
    b = LakebaseBrowser("h", None, http=http)
    row = run(b.project("a", "tok"))
    assert row["pgVersion"] == 17 and row["defaultBranch"] == "production"
    assert row["displayName"] == "Tickets"


def test_a_branch_list_marks_the_default():
    http = FakeHttp({"/api/2.0/postgres/projects/a/branches": {"branches": [
        {"name": "projects/a/branches/production", "status": {"state": "READY"}},
        {"name": "projects/a/branches/agent-9"},
    ]}})
    rows = run(LakebaseBrowser("h", None, http=http).branches("a", "tok"))
    assert [r["name"] for r in rows] == ["production", "agent-9"]
    assert rows[0]["isDefault"] and not rows[1]["isDefault"]


def test_a_compute_reads_its_host_and_range():
    http = FakeHttp({"/api/2.0/postgres/projects/a/branches/b/endpoints": {"endpoints": [{
        "name": "projects/a/branches/b/endpoints/primary",
        "status": {"endpoint_type": "ENDPOINT_TYPE_READ_WRITE", "current_state": "ACTIVE",
                   "hosts": {"host": "ep-cool.example"},
                   "autoscaling_limit_min_cu": 0.5, "autoscaling_limit_max_cu": 4}}]}})
    rows = run(LakebaseBrowser("h", None, http=http).endpoints("a", "b", "tok"))
    assert rows[0]["host"] == "ep-cool.example" and rows[0]["rangeValid"]
    assert "0.5 – 4" in rows[0]["range"]


def test_a_project_page_survives_one_failing_block():
    """[UI-3], [E-11] Four independent reads; one denial must not blank the other three."""
    http = FakeHttp({
        "/api/2.0/postgres/projects/a": {"name": "projects/a", "status": {"state": "READY"}},
        "/api/2.0/postgres/projects/a/branches": PermissionError("you do not have CAN MANAGE"),
        "/api/2.0/postgres/projects/a/branches/production/databases": {"databases": []},
        "/api/2.0/postgres/projects/a/branches/production/endpoints": {"endpoints": []},
    })
    blocks = run(page_blocks("tok", "a", "production", LakebaseBrowser("h", None, http=http)))
    assert blocks["project"]["state"] == "ready"
    assert "CAN MANAGE" in blocks["branches"]["error"]
    assert blocks["databases"] == [] and blocks["compute"] == []


def test_the_cache_is_per_credential():
    """[E-28] The token is the permission boundary: no user's results may answer another's request."""
    http = FakeHttp({"/api/2.0/postgres/projects/a": {"name": "projects/a", "status": {"state": "READY"}}})
    b = LakebaseBrowser("h", None, http=http)
    run(b.project("a", "token-alice"))
    run(b.project("a", "token-bob"))
    assert len(http.calls) == 2, "a cache entry was shared across two credentials"


def test_the_cache_is_dropped_on_refresh():
    """[E-27] A deleted object is visible for at most the TTL, and never after a manual refresh."""
    http = FakeHttp({"/api/2.0/postgres/projects/a": {"name": "projects/a", "status": {"state": "READY"}}})
    b = LakebaseBrowser("h", None, http=http)
    run(b.project("a", "tok"))
    run(b.project("a", "tok"))
    assert len(http.calls) == 1, "the second read should have been cached"
    b.invalidate("tok", "project:")
    run(b.project("a", "tok"))
    assert len(http.calls) == 2


# -- Apps ----------------------------------------------------------------------------------------
def test_a_deployment_that_failed_makes_the_app_failing_even_when_it_is_up():
    """The case that wastes the most user time: the app is serving something wrong."""
    state, raw = state_of({"app_status": {"state": "RUNNING"},
                           "active_deployment": {"status": {"state": "FAILED"}}})
    assert state == "failing" and raw == "FAILED"


def test_a_running_app_with_a_good_deployment_is_running():
    assert state_of({"app_status": {"state": "RUNNING"},
                     "active_deployment": {"status": {"state": "SUCCEEDED"}}})[0] == "running"


@pytest.mark.parametrize("status,ms,timeout,word", [
    (200, 400, False, "running"),
    (200, 12_000, False, "starting"),      # answered, but slowly: a cold start waking
    (None, 15_000, True, "starting"),      # no answer yet, which is legitimate
    (500, 300, False, "failing"),
    (None, 10, False, "unreachable"),
])
def test_health_has_five_distinct_words(status, ms, timeout, word):
    """[AP-4], [E-14] `starting` exists so a cold app is not reported as broken."""
    assert health_word(status, ms, timeout) == word


def test_the_apps_list_reads_the_resource_from_the_list_payload():
    """[06 §6.2] "Which app uses this project" must be O(n) items in one response, not O(n) calls."""
    http = FakeHttp({"/api/2.0/apps": {"apps": [
        {"name": "tickets", "url": "t-1.example", "app_status": {"state": "RUNNING"},
         "resources": [{"name": "postgres", "postgres": {
             "branch": "projects/pg/branches/production", "permission": "CAN_CONNECT_AND_CREATE"}}]},
        {"name": "orders", "url": "o-1.example", "app_status": {"state": "STOPPED"}, "resources": []},
    ]}})
    rows = run(AppsBrowser("h", None, http=http).apps("tok"))
    assert len(http.calls) == 1
    assert rows[0]["lakebase"] == "pg" and rows[0]["state"] == "running"
    assert rows[0]["url"] == "https://t-1.example"
    assert apps_using(rows, "pg")[0]["name"] == "tickets"
    assert apps_using(rows, "") == []


def test_a_postgres_resource_reports_its_permission():
    http = FakeHttp({"/api/2.0/apps/tickets": {
        "name": "tickets", "app_status": {"state": "RUNNING"},
        "active_deployment": {"status": {"state": "SUCCEEDED"}},
        "resources": [{"name": "postgres", "postgres": {
            "branch": "projects/pg/branches/b", "permission": "CAN_CONNECT_AND_CREATE"}}]}})
    row = run(AppsBrowser("h", None, http=http).app("tickets", "tok"))
    assert row["resources"][0]["kind"] == "postgres"
    assert row["resources"][0]["permission"] == "CAN_CONNECT_AND_CREATE"
    assert row["deploymentState"] == "SUCCEEDED"


def test_a_postgres_resource_points_at_a_branch():
    """[E-15] A resource naming a deleted branch must be visible as such, not silently ignored."""
    http = FakeHttp({"/api/2.0/apps/tickets": {
        "name": "tickets", "resources": [{"name": "postgres", "postgres": {
            "branch": "projects/pg/branches/gone", "permission": "CAN_CONNECT_AND_CREATE"}}]}})
    row = run(AppsBrowser("h", None, http=http).app("tickets", "tok"))
    assert row["resources"][0]["branch"].endswith("/branches/gone")
