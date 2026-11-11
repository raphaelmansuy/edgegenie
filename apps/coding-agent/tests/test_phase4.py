"""Phase 4: hooks, a second server, citations, schedules, subagents. `[R-13]` `[R-19]` `[R-20]` `[R-23]` `[R-25]`.

Every one of these is a **narrowing**, and each test below fails the permissive version:

  * a hook that silently disappears rather than raising;
  * a `then: run` that executes without an administrator;
  * a second server that is mutable, or whose tools are summed into the core budget;
  * a schedule that auto-approves;
  * a subagent wider than its parent.
"""

from __future__ import annotations

import pytest

from api.domain.extension import (
    Ceiling, DocHit, Schedule, Server, Subagent, attribution, cite, may_attach, may_start,
    plan_run, rank_docs, tool_budget,
)
from api.domain.hooks import Call, RuleError, evaluate, parse


# ============================================================== [R-13] hooks
RULES = [
    {"name": "block-delete-on-gold", "on": "before_tool", "match": {"tool": "dbx_run_sql"},
     "when": {"matches": {"field": "sql", "value": r"(?i)^\s*delete\s+from\s+main\.gold\."}},
     "then": "refuse", "say": "main.gold is append-only. Write to a branch and merge."},
    {"name": "allow-describe", "on": "before_tool", "match": {"tool": "dbx_describe_table"},
     "then": "allow"},
]


def test_a_rule_refuses_a_matching_call_and_quotes_its_own_sentence():
    rules = parse(RULES)
    v = evaluate(rules, Call("dbx_run_sql", {"sql": "DELETE FROM main.gold.sales"}))
    assert v.outcome == "refuse"
    assert v.rule == "block-delete-on-gold"
    assert v.say == "main.gold is append-only. Write to a branch and merge."


def test_a_rule_does_not_touch_a_call_it_does_not_match():
    rules = parse(RULES)
    assert evaluate(rules, Call("dbx_run_sql", {"sql": "INSERT INTO main.gold.sales VALUES (1)"})).allowed


def test_an_allow_rule_stops_later_rules_from_firing():
    """First match wins: a platform team's explicit allow is the end of the decision."""
    rules = parse(RULES + [{"name": "catch-all", "match": {"tool": "^dbx_"}, "then": "refuse"}])
    assert evaluate(rules, Call("dbx_describe_table", {})).rule == "allow-describe"


def test_the_agents_next_attempt_is_not_blocked_by_a_rule_it_avoided():
    """A refusal must be actionable: a statement the rule does not match passes."""
    rules = parse(RULES)
    assert evaluate(rules, Call("dbx_run_sql", {"sql": "MERGE INTO main.silver.s USING x ON 1=1"})).allowed


def test_run_is_refused_unless_an_administrator_allowed_it():
    """A program inside the tool server is an administrator's decision (`[E-16]`). The default is no."""
    rules = parse([{"name": "fmt", "match": {"tool": "dbx_write_notebook"}, "then": "run",
                    "run": ["ruff", "format"]}])
    v = evaluate(rules, Call("dbx_write_notebook", {"path": "/x"}))
    assert v.outcome == "refuse"
    assert "administrator" in v.say
    assert evaluate(rules, Call("dbx_write_notebook", {"path": "/x"}), allow_run=True).outcome == "run"


@pytest.mark.parametrize("bad,message", [
    ([{"name": "x", "on": "whenever"}], "before_tool or after_tool"),
    ([{"name": "x"}, {"name": "x"}], "declared twice"),
    ([{"on": "before_tool"}], "no name"),
    ([{"name": "x", "then": "maybe"}], "refuse, allow or run"),
    ([{"name": "x", "then": "run"}], "needs a `run` program"),
    ([{"name": "x", "when": {"wat": 1}}], "no known operator"),
    (["not a mapping"], "not a mapping"),
])
def test_a_bad_rule_is_an_ERROR_not_an_omission(bad, message):
    """A hook that silently disappears is a rule a platform team believes is enforcing something."""
    with pytest.raises(RuleError, match=message):
        parse(bad)


def test_an_empty_file_is_no_rules():
    assert parse(None) == [] and parse([]) == []


def test_a_bad_regex_does_not_fire_and_does_not_crash():
    """An unevaluable rule must never decide the fence."""
    rules = parse([{"name": "bad", "match": {"tool": "dbx_run_sql"},
                    "when": {"matches": {"field": "sql", "value": "([unclosed"}}}])
    assert evaluate(rules, Call("dbx_run_sql", {"sql": "anything"})).allowed


def test_an_absent_argument_makes_a_condition_false_not_an_error():
    rules = parse(RULES)
    assert evaluate(rules, Call("dbx_run_sql", {})).allowed


def test_after_tool_rules_only_run_in_their_phase():
    rules = parse([{"name": "post", "on": "after_tool", "match": {"tool": "dbx_run_sql"},
                    "then": "refuse"}])
    assert evaluate(rules, Call("dbx_run_sql", {}), phase="before_tool").allowed
    assert evaluate(rules, Call("dbx_run_sql", {}), phase="after_tool").outcome == "refuse"


def test_every_operator_works():
    checks = [
        ({"equals": {"field": "tool", "value": "t"}}, True),
        ({"starts_with": {"field": "tool", "value": "t"}}, True),
        ({"starts_with": {"field": "tool", "value": "tx"}}, False),
        ({"contains": {"field": "sql", "value": "delete"}}, True),
        ({"in": {"field": "tool", "value": ["a", "t"]}}, True),
        ({"not": {"equals": {"field": "tool", "value": "other"}}}, True),
        ({"all": [{"equals": {"field": "tool", "value": "t"}}]}, True),
        ({"any": [{"equals": {"field": "tool", "value": "no"}}, {"equals": {"field": "tool", "value": "t"}}]}, True),
    ]
    for when, want in checks:
        rules = parse([{"name": "r", "match": {"tool": "t"}, "when": when, "then": "refuse"}])
        got = not evaluate(rules, Call("t", {"sql": "delete from x"})).allowed
        assert got is want, f"{when} -> {got}"


# ============================================================== [R-19] a second server
def test_an_unapproved_server_cannot_be_attached():
    ok, why = may_attach(Server("someone/third-party", read_only=True), allowed={"genie"})
    assert not ok and "approved servers" in why


def test_a_mutable_foreign_server_cannot_be_attached():
    """The fence IS "this process was started with one folder and one schema". A server without that
    cannot be allowed to change anything."""
    ok, why = may_attach(Server("genie", read_only=False), allowed={"genie"})
    assert not ok and "cannot fence" in why


def test_an_approved_read_only_server_may_be_attached():
    assert may_attach(Server("genie", read_only=True, tools=4), allowed={"genie"}) == (True, "")


def test_the_tool_budget_is_per_server_never_a_sum_in_one_number():
    """`[R-19]`: summing would make the 28-tool budget pass while the agent advertised twice the schemas."""
    b = tool_budget([Server("genie", True, 4)], 28)
    assert [r["server"] for r in b["servers"]] == ["built-in", "genie"]
    assert b["servers"][0]["tools"] == 28
    assert b["total"] == 32, "the total is shown, but the budget test reads the built-in row"


# ============================================================== [R-20] citations
def _hit(score: int, title: str = "T") -> DocHit:
    return DocHit(f"docs/{title}.md", title, f"https://x/{title}", score, "excerpt")


def test_docs_rank_best_first_and_respect_the_limit():
    assert [h.title for h in rank_docs([_hit(1, "a"), _hit(9, "b"), _hit(5, "c")], limit=2)] == ["b", "c"]


def test_ties_keep_input_order_so_a_result_is_stable():
    assert [h.title for h in rank_docs([_hit(5, "a"), _hit(5, "b")])] == ["a", "b"]


def test_a_citation_renders_as_a_link_a_reader_can_click():
    line = cite(_hit(1, "security"), section="the fence").line()
    assert line == "[security › the fence](https://x/security)"


def test_a_citation_without_a_section_still_names_the_page():
    assert cite(_hit(1, "glossary")).line() == "[glossary](https://x/glossary)"


# ============================================================== [R-23] schedules
def test_a_schedule_runs_as_its_creator():
    d = plan_run(Schedule("s", "check the pipeline", "dana@x", cron="0 6 * * *"))
    assert d.outcome == "run" and d.identity == "dana@x"


def test_a_schedule_with_no_owner_is_refused():
    """No identity, no run: a scheduled job that acts as nobody is a job nobody can audit."""
    assert plan_run(Schedule("s", "x", "")).outcome == "refused"


def test_a_schedule_with_no_prompt_is_refused():
    assert plan_run(Schedule("s", "  ", "dana@x")).outcome == "refused"


def test_a_schedule_in_ask_mode_is_narrowed_to_read_only():
    """`[R-23]`: an unattended run has nobody to ask, and Genie's scheduled tasks auto-approve always.
    Narrowing is the safe answer; refusing the whole schedule would be worse for a legitimate read task."""
    d = plan_run(Schedule("s", "x", "dana@x", write_mode="ask"))
    assert d.outcome == "run" and d.mode == "read-only"


@pytest.mark.parametrize("mode", ["read-only", "fenced", "ask", "", "nonsense"])
def test_a_run_is_never_WIDER_than_its_schedule(mode):
    d = plan_run(Schedule("s", "x", "dana@x", write_mode=mode))
    assert d.mode in ("read-only", "fenced")
    if mode == "read-only":
        assert d.mode == "read-only"


# ============================================================== [R-25] subagents
def test_a_subagent_may_not_outlive_its_parents_budget():
    ok, why = may_start(Subagent("p", "find revenue", Ceiling(tokens=900_000)), parent_tokens_left=100_000)
    assert not ok and "left" in why


def test_a_subagent_must_narrow_the_scope_never_widen_it():
    assert not may_start(Subagent("p", "x", scope="main.other"),
                         parent_tokens_left=10**6, parent_scope="main.gold")[0]
    assert may_start(Subagent("p", "x", scope="main.gold.sub"),
                     parent_tokens_left=10**6, parent_scope="main.gold")[0]


def test_a_scope_check_understands_a_folder_and_a_catalog_name():
    """One separator is a path, the other is a Unity Catalog name. A check that knew only `/` refused the
    common case."""
    assert may_start(Subagent("p", "x", scope="/Users/me/p/sub"),
                     parent_tokens_left=10**6, parent_scope="/Users/me/p")[0]
    assert may_start(Subagent("p", "x", scope="main.gold.orders"),
                     parent_tokens_left=10**6, parent_scope="main.gold")[0]


def test_a_prefix_that_is_not_a_child_is_refused():
    """`main.goldx` is not inside `main.gold`, and a `startswith` without the separator would say it is."""
    assert not may_start(Subagent("p", "x", scope="main.goldx"),
                         parent_tokens_left=10**6, parent_scope="main.gold")[0]


def test_a_subagent_needs_an_objective_and_a_ceiling():
    assert not may_start(Subagent("p", "  "), parent_tokens_left=1000)[0]
    assert not may_start(Subagent("p", "x", Ceiling(tokens=0)), parent_tokens_left=1000)[0]
    assert not may_start(Subagent("p", "x", Ceiling(seconds=0)), parent_tokens_left=1000)[0]


def test_a_subagents_calls_appear_as_one_attributed_group():
    a = attribution(Subagent("parent-1", "find the revenue table"))
    assert a["parent"] == "parent-1"
    assert a["collapsed"] is True
    assert a["ceiling"]["tokens"] > 0


# ============================================================== [R-20] the corpus and the route
def test_the_documentation_corpus_is_found_and_indexed():
    """A fixed `parents[n]` indexed NOTHING and every search returned zero hits while reporting success —
    so the first assertion is that the corpus is non-empty."""
    from api.services import docsearch

    docs = docsearch.build()
    assert len(docs) > 20, f"only {len(docs)} documents indexed; the root is probably wrong"
    assert any(d["path"].startswith("docs/") for d in docs)


def test_a_search_finds_a_real_document_and_explains_why():
    from api.services import docsearch

    hits = docsearch.search("fence")
    assert hits, "no document mentions the fence"
    assert hits[0].path.endswith(".md")
    assert hits[0].excerpt, "a hit must carry the words that matched"


def test_a_search_is_an_AND_and_an_unknown_word_finds_nothing():
    from api.services import docsearch

    assert docsearch.search("fence schema")
    assert docsearch.search("kubernetes-helm-not-in-this-repo") == []


@pytest.fixture()
def client():
    """The repository's one TestClient builder. Declared here rather than in a conftest because only this
    file needs an HTTP client, and a shared fixture would make every suite pay for an app it does not use."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from test_api import make_client

    return make_client()


def test_the_docs_route_answers(client):
    r = client.get("/api/docs/search", params={"q": "fence"})
    assert r.status_code == 200
    body = r.json()
    assert body["query"] == "fence"
    for hit in body["hits"]:
        assert set(hit) >= {"path", "title", "url", "score", "excerpt"}
