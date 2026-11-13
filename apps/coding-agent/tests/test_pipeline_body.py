"""The pipeline spec rules, as a table. Pure: no transport, no environment.

Each row is a spec that came back from somewhere: a model, a skill, a half-remembered example. The
interesting rows are the refusals, because every one of them is a platform `400` avoided — and the
platform's sentence for each is accurate and hard to act on, which is why the refusal is ours.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

BODY = Path(__file__).resolve().parents[1] / "tools" / "pipeline_body.py"


def load():
    spec = importlib.util.spec_from_file_location("pipeline_body_under_test", BODY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


p = load()

NOTEBOOKS = ["/Users/me/agent_scratch/sales/bronze", "/Users/me/agent_scratch/sales/silver"]


# ---------------------------------------------------------------------------------------------
# the happy body
# ---------------------------------------------------------------------------------------------
def test_a_minimal_serverless_body_is_exactly_the_documented_shape():
    body = p.build("sales_medallion", notebooks=NOTEBOOKS, catalog="main", schema="sales")
    assert body["name"] == "sales_medallion"
    assert body["serverless"] is True
    assert body["edition"] == "ADVANCED"
    assert body["catalog"] == "main"
    assert body["schema"] == "sales"
    assert body["libraries"] == [{"notebook": {"path": NOTEBOOKS[0]}},
                                 {"notebook": {"path": NOTEBOOKS[1]}}]


def test_clusters_is_absent_not_empty():
    """The platform rejects `clusters` alongside `serverless`; an empty list reads as classic compute with
    no settings. The only correct body has no key at all."""
    body = p.build("x", notebooks=NOTEBOOKS[:1], catalog="main", schema="s")
    assert "clusters" not in body


def test_a_file_library_is_accepted():
    body = p.build("x", files=["/Users/me/agent_scratch/x/transform.sql"], catalog="main", schema="s")
    assert body["libraries"] == [{"file": {"path": "/Users/me/agent_scratch/x/transform.sql"}}]


def test_a_glob_library_is_accepted_because_a_bundle_uses_one():
    body = p.build("x", glob="/Users/me/agent_scratch/x/**/*.py", catalog="main", schema="s")
    assert body["libraries"] == [{"glob": {"include": "/Users/me/agent_scratch/x/**/*.py"}}]


def test_the_edition_is_upper_cased_rather_than_refused_for_case():
    body = p.build("x", notebooks=NOTEBOOKS[:1], catalog="main", schema="s", edition="advanced")
    assert body["edition"] == "ADVANCED"


# ---------------------------------------------------------------------------------------------
# the refusals, each with the sentence it must contain
# ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kwargs,expected", [
    ({"notebooks": NOTEBOOKS, "catalog": "", "schema": "sales"}, "Unity Catalog"),
    ({"notebooks": NOTEBOOKS, "catalog": "main", "schema": ""}, "schema"),
    ({"notebooks": [], "files": [], "catalog": "main", "schema": "s"}, "at least one library"),
    ({"notebooks": NOTEBOOKS, "catalog": "main", "schema": "s", "edition": "ENTERPRISE"}, "edition"),
    ({"notebooks": ["relative/path"], "catalog": "main", "schema": "s"}, "absolute"),
    ({"notebooks": NOTEBOOKS, "catalog": "main", "schema": "s", "serverless": False}, "classic"),
])
def test_every_refusal_names_what_to_change(kwargs, expected):
    with pytest.raises(p.PipelineProblem) as caught:
        p.build("x", **kwargs)
    assert expected in str(caught.value)


def test_a_serverless_refusal_explains_the_unity_catalog_requirement():
    """[RB-8], [E-4]: a user who does not know serverless always uses UC reads the platform's catalog
    error and looks in the wrong place."""
    with pytest.raises(p.PipelineProblem) as caught:
        p.build("x", notebooks=NOTEBOOKS, catalog="", schema="sales")
    message = str(caught.value)
    assert "catalog='main'" in message


def test_the_write_fence_is_applied_to_every_library_path():
    """The rule is supplied by the caller so this module stays pure, which is also why this test can
    assert it was CALLED rather than assert a side effect."""
    seen: list[str] = []

    def check(path: str) -> None:
        seen.append(path)
        if "/Shared/" in path:
            raise PermissionError("write blocked: outside the fence")

    p.build("x", notebooks=NOTEBOOKS, catalog="main", schema="s", check_path=check)
    assert seen == NOTEBOOKS

    with pytest.raises(PermissionError):
        p.build("x", notebooks=["/Shared/someone/x"], catalog="main", schema="s", check_path=check)


def test_an_empty_name_is_refused():
    with pytest.raises(p.PipelineProblem, match="name"):
        p.build("", notebooks=NOTEBOOKS, catalog="main", schema="s")


# ---------------------------------------------------------------------------------------------
# describing and diffing libraries
# ---------------------------------------------------------------------------------------------
def test_describe_libraries_reads_every_shape():
    body = {"libraries": [{"notebook": {"path": "/a"}}, {"file": {"path": "/b"}},
                          {"glob": {"include": "/c/*.py"}}]}
    assert p.describe_libraries(body) == ["/a", "/b", "/c/*.py"]


def test_an_edit_that_removes_a_library_names_it():
    """[E-18] A dropped library's tables stop being maintained. Not refused — the user may have asked —
    but impossible to do silently."""
    before = {"libraries": [{"notebook": {"path": "/a"}}, {"notebook": {"path": "/b"}}]}
    after = {"libraries": [{"notebook": {"path": "/a"}}]}
    assert p.removed_libraries(before, after) == ["/b"]


def test_an_edit_that_adds_a_library_removes_nothing():
    before = {"libraries": [{"notebook": {"path": "/a"}}]}
    after = {"libraries": [{"notebook": {"path": "/a"}}, {"notebook": {"path": "/b"}}]}
    assert p.removed_libraries(before, after) == []


# ---------------------------------------------------------------------------------------------
# the update body
# ---------------------------------------------------------------------------------------------
def test_full_refresh_is_always_a_boolean_never_omitted():
    """The difference between 're-read new data' and 're-read every source' must never be a platform
    default the caller did not see (spec 014 [PIPE-3])."""
    assert p.start_body() == {"full_refresh": False}
    assert p.start_body(full_refresh=True) == {"full_refresh": True}


def test_validate_only_is_carried_and_runs_nothing():
    assert p.start_body(validate_only=True) == {"full_refresh": False, "validate_only": True}


def test_a_selection_is_carried():
    assert p.start_body(refresh_selection=["main.sales.orders"]) == {
        "full_refresh": False, "refresh_selection": ["main.sales.orders"]}


@pytest.mark.parametrize("kwargs", [
    {"full_refresh": True, "refresh_selection": ["t"]},
    {"validate_only": True, "refresh_selection": ["t"]},
])
def test_two_modes_at_once_is_refused_rather_than_sent(kwargs):
    with pytest.raises(p.PipelineProblem):
        p.start_body(**kwargs)
