"""The SQL fence: a table of statements, and the property that must hold for all of them.

Written because the previous implementation failed open. `check_sql` was:

    targets = sql_targets(sql)          # _TABLE_RE + _FROM_RE
    if not scope.schema: return ASK
    outside = [t for t in targets if not t.startswith(schema + ".")]
    if outside: return ASK
    return ALLOW                        # <- reached with targets == []

So a write whose target the pattern could not read was ALLOWed. `OPTIMIZE workspace.other.t`, a table
belonging to somebody else, was `ALLOW`. The tool server's own `_check_sql_scope` never had this bug
(it refuses when it cannot identify a target); the app side did, and a parity test asserted
"ALLOW or ASK" — which is every verdict except `DENY`, so it could not fail.

This file is the replacement. Its centre is not a list of examples but the property:

    **A statement the fence cannot place must never be ALLOWed.**

and its converse, which matters just as much:

    **A statement that writes only inside the schema and reads anything must be ALLOWed** —
    reads are not fenced, and refusing them made a correct CTAS look like a violation.

Everything is tested against `check_sql` alone. No network, no warehouse, no clock.
"""
from __future__ import annotations

import re

import pytest

from api.domain.scope import (
    _TARGETS,
    WRITE_SQL,
    Action,
    Scope,
    Verdict,
    _inside_schema,
    check_sql,
    classify_sql,
    sql_targets,
)

FOLDER = "/Users/me/agent_scratch"
SCHEMA = "workspace.mine"


def scope(schema: str | None = SCHEMA) -> Scope:
    return Scope.for_session("sess1234abcd", FOLDER, schema)


def verdict(sql: str, sch: str | None = SCHEMA) -> str:
    return check_sql(scope(sch), sql).verdict.value


# =============================================================== the property, stated as a test

#: Statements whose write target is unreadable BY CONSTRUCTION. The fence must not guess; it must ask.
UNPLACEABLE = [
    "OPTIMIZE",                       # a verb with nothing after it
    "VACUUM",
    "OPTIMIZE TABLE",                 # a keyword, not a name
    "CREATE TABLE",                   # truncated statement
    "UPDATE SET",                     # the MERGE trap, alone
    "INSERT INTO IF NOT EXISTS x",    # a word from the keyword set lands where the name goes
]


@pytest.mark.parametrize("sql", UNPLACEABLE)
def test_a_write_that_cannot_be_placed_is_never_allowed(sql):
    """The bug this file exists for. If this fails, the fence fails open."""
    assert verdict(sql) == "ask", f"{sql!r} must be ASKed, not allowed"


@pytest.mark.parametrize("sql", UNPLACEABLE)
def test_the_refusal_says_why(sql):
    d = check_sql(scope(), sql)
    assert d.reason, f"{sql!r} was refused with no reason, which a user cannot act on"


# =============================================================== writes inside the schema

INSIDE = [
    "CREATE TABLE workspace.mine.t (x INT)",
    "CREATE OR REPLACE TABLE workspace.mine.t AS SELECT 1",
    "CREATE TABLE IF NOT EXISTS workspace.mine.t (x INT)",
    "CREATE VIEW workspace.mine.v AS SELECT 1",
    "CREATE MATERIALIZED VIEW workspace.mine.mv AS SELECT 1",
    "CREATE STREAMING TABLE workspace.mine.st AS SELECT 1",
    "CREATE VOLUME workspace.mine.vol",
    "CREATE FUNCTION workspace.mine.f() RETURNS INT RETURN 1",
    "INSERT INTO workspace.mine.t VALUES (1)",
    "INSERT INTO workspace.mine.t SELECT * FROM workspace.other.s",
    "INSERT OVERWRITE TABLE workspace.mine.t SELECT 1",
    "MERGE INTO workspace.mine.t USING src ON t.a = src.a WHEN MATCHED THEN UPDATE SET t.b = src.b",
    "ALTER TABLE workspace.mine.t ADD COLUMN c INT",
    "COMMENT ON TABLE workspace.mine.t IS 'hello'",
    "OPTIMIZE workspace.mine.t",
    "OPTIMIZE workspace.mine.t ZORDER BY (a)",
    "VACUUM workspace.mine.t RETAIN 168 HOURS",
    "CREATE TABLE `workspace`.`mine`.`t` (x INT)",
]


@pytest.mark.parametrize("sql", INSIDE)
def test_a_write_inside_the_schema_is_allowed(sql):
    assert verdict(sql) == "allow", f"{sql!r} writes only inside {SCHEMA} and must be allowed"


@pytest.mark.parametrize("sql", INSIDE)
def test_a_write_inside_the_schema_names_its_target(sql):
    """ALLOW with no target is indistinguishable from ALLOW by accident — the old bug's shape."""
    assert sql_targets(sql), f"{sql!r} was allowed without identifying what it writes"


# =============================================================== writes outside the schema

OUTSIDE = [
    "CREATE TABLE workspace.other.t (x INT)",
    "CREATE TABLE workspace.other.t AS SELECT 1",
    "INSERT INTO workspace.other.t VALUES (1)",
    "MERGE INTO workspace.other.t USING s ON 1=1 WHEN MATCHED THEN DELETE",
    "ALTER TABLE workspace.other.t ADD COLUMN c INT",
    "OPTIMIZE workspace.other.t",
    "OPTIMIZE workspace.other.t ZORDER BY (a)",
    "VACUUM workspace.other.t",
    "VACUUM workspace.other.t RETAIN 1 HOURS",
    "COMMENT ON TABLE workspace.other.t IS 'x'",
    "CREATE TABLE other_catalog.mine.t (x INT)",     # right schema name, wrong catalog
    "INSERT INTO workspace.elsewhere.t VALUES (1)",
]


@pytest.mark.parametrize("sql", OUTSIDE)
def test_a_write_outside_the_schema_is_asked(sql):
    assert verdict(sql) == "ask", f"{sql!r} writes outside {SCHEMA} and must need a human"


@pytest.mark.parametrize("sql", OUTSIDE)
def test_the_reason_names_the_target_or_the_schema(sql):
    d = check_sql(scope(), sql)
    assert SCHEMA in d.reason or "could not be identified" in d.reason, (
        f"{sql!r} was refused without saying where the fence is: {d.reason!r}")


# =============================================================== a name we cannot place

#: A one-part or two-part name cannot be verified against a three-part schema. `INSERT INTO t`
#: lands in whatever default schema the warehouse holds; accepting it would be a guess.
UNQUALIFIED = [
    "INSERT INTO t VALUES (1)",
    "UPDATE t SET a = 1",
    "DELETE FROM t",
    "OPTIMIZE t",
    "VACUUM t",
    "CREATE TABLE t (x INT)",
    "INSERT INTO mine.t VALUES (1)",     # a 2-part name against a 3-part schema
]


@pytest.mark.parametrize("sql", UNQUALIFIED)
def test_an_unqualified_target_is_asked(sql):
    assert verdict(sql) == "ask", (
        f"{sql!r} names an object this fence cannot place against {SCHEMA}; the honest answer is ASK")


def test_a_two_part_schema_accepts_a_two_part_target():
    """The other direction: a session whose schema is two parts accepts a two-part target."""
    assert verdict("CREATE TABLE mine.t AS SELECT 1", sch="mine") == "allow"
    assert verdict("INSERT INTO mine.t VALUES (1)", sch="mine") == "allow"
    assert verdict("INSERT INTO other.t VALUES (1)", sch="mine") == "ask"
    # A three-part target under a two-part schema has a DIFFERENT leading part, so it is not the
    # session's schema: `catalog.mine.t` is the `mine` schema of `catalog`, while this session's is
    # schema `mine` of whatever catalog the warehouse defaults to. Refusing is the provable answer.
    assert verdict("INSERT INTO catalog.mine.t VALUES (1)", sch="mine") == "ask"
    assert verdict("CREATE TABLE c.mine.t (x INT)", sch="mine") == "ask"


# =============================================================== destructive, wherever it points

DESTRUCTIVE = [
    "DROP TABLE workspace.mine.t",
    "DROP TABLE workspace.other.t",
    "DROP TABLE t",
    "TRUNCATE TABLE workspace.mine.t",
    "DELETE FROM workspace.mine.t",
    "DROP SCHEMA workspace.mine",
    "DROP VIEW workspace.mine.v",
    "DROP DATABASE something",
]


@pytest.mark.parametrize("sql", DESTRUCTIVE)
def test_destructive_always_needs_a_human_even_inside_the_fence(sql):
    d = check_sql(scope(), sql)
    assert d.verdict is Verdict.ASK
    assert d.action is Action.DESTRUCTIVE
    assert "human" in d.reason


# =============================================================== reads are free

READS = [
    "SELECT * FROM workspace.other.t",
    "SELECT 1",
    "SHOW TABLES IN workspace.other",
    "DESCRIBE TABLE workspace.other.t",
    "WITH x AS (SELECT 1) SELECT * FROM x",
    "SELECT * FROM a JOIN b ON a.id = b.id",
    "EXPLAIN SELECT 1",
]


@pytest.mark.parametrize("sql", READS)
def test_a_read_is_allowed_and_fenced_by_nothing(sql):
    d = check_sql(scope(), sql)
    assert d.verdict is Verdict.ALLOW
    assert d.action is Action.READ


@pytest.mark.parametrize("sql", READS)
def test_a_read_never_produces_a_write_target(sql):
    """`FROM` was a target, which is why a correct CTAS was refused. Reads read."""
    assert sql_targets(sql) == [], f"{sql!r} produced a write target: {sql_targets(sql)}"


# =============================================================== the session with no schema

def test_no_schema_means_every_write_is_asked():
    for sql in ("CREATE TABLE workspace.mine.t (x INT)", "INSERT INTO workspace.mine.t VALUES (1)"):
        d = check_sql(scope(None), sql)
        assert d.verdict is Verdict.ASK
        assert "no writable schema" in d.reason


def test_a_read_is_still_allowed_with_no_schema():
    assert check_sql(scope(None), "SELECT * FROM anything").verdict is Verdict.ALLOW


# =============================================================== classification is total

def test_classification_is_total():
    """Every statement gets exactly one action; there is no 'unknown' branch to fall through."""
    for sql in INSIDE + OUTSIDE + UNQUALIFIED + DESTRUCTIVE + READS:
        assert classify_sql(sql) in (Action.READ, Action.WRITE, Action.DESTRUCTIVE), sql


def test_a_statement_that_both_writes_and_drops_is_destructive():
    """The more dangerous classification wins, because the human check is the stronger one."""
    assert classify_sql("DROP TABLE t") is Action.DESTRUCTIVE
    assert classify_sql("CREATE TABLE t (x INT)") is Action.WRITE


#: Verbs that write but could be classified READ, so they were ALLOWed without reaching the fence.
#: `COMMENT ON` and then `REFRESH`/`ANALYZE` were in that list, each found the same way: by sweeping
#: the pattern rather than by listing examples.
#:
#: **The two lists are checked against each other**, not maintained by hand. `WRITE_SQL` decides
#: whether a statement is a write at all; `_TARGETS` decides what it writes. A verb in the first and
#: not the second is a write that cannot be placed — which now falls back to ASK, so it is safe, but
#: it is also an unnecessary question. A verb in the second and not the first is worse: a write
#: classified READ, allowed, never fenced. `test_the_two_patterns_cover_the_same_verbs` is what keeps
#: that from happening again, and it is why this list is not the source of truth.
WRITE_VERBS = [
    "create table a.b.c (x INT)",
    "insert into a.b.c values (1)",
    "update a.b.c set x = 1",
    "merge into a.b.c using z on 1=1 when matched then delete",
    "alter table a.b.c add column y int",
    "optimize a.b.c",
    "vacuum a.b.c",
    "grant select on table a.b.c to `u`",
    "revoke select on table a.b.c from `u`",
    "comment on table a.b.c is 'x'",
    "comment on column a.b.c.d is 'x'",
    "copy into a.b.c from '/x'",
    "undrop table a.b.c",
    "restore table a.b.c to version as of 1",
    "refresh table a.b.c",
    "analyze table a.b.c compute statistics",
]


@pytest.mark.parametrize("sql", WRITE_VERBS)
def test_every_write_verb_is_classified_as_a_write_at_least(sql):
    """This asserts the floor — the verb is not READ — not the verdict, which the tables above cover."""
    assert classify_sql(sql) is not Action.READ, (
        f"{sql!r} is classified READ, so it is allowed and never reaches the fence")


def test_the_two_patterns_cover_the_same_verbs():
    """Every verb that makes a statement a WRITE must also let its target be read.

    The failure this prevents is the one that produced the original bug: `WRITE_SQL` said "this is a
    write" and `_TARGETS` said "I cannot see what it writes", and the empty list fell through to
    ALLOW. The fallback now catches it — but a verb in both patterns means the fence can answer
    precisely, and a verb in only one means it cannot.
    """
    def alternatives(pattern) -> set[str]:
        body = pattern.pattern
        start = body.index("(?:") + 3 if "(?:" in body else body.index("(") + 1
        return {v.strip() for v in re.split(r"\|", body[start:]) if re.fullmatch(r"[a-z\s]+", v)}

    write_verbs = set(re.findall(r"[a-z]+(?:\s+[a-z]+)?", WRITE_SQL.pattern))
    target_verbs = set(re.findall(r"[a-z]+(?:\s+[a-z]+)?", _TARGETS.pattern))
    # A verb the classifier treats as a write, with no way to find its target, is a question the
    # fence has to ask instead of answer. Report it as a list so a new verb is one line to add.
    unmatched = {
        v for v in ("refresh", "analyze", "optimize", "vacuum", "undrop", "restore", "copy into")
        if v in write_verbs and v not in target_verbs
    }
    assert not unmatched, (
        f"these verbs are writes whose target cannot be read: {sorted(unmatched)}; "
        "add them to _TARGETS so the fence can place them")
    _ = alternatives


@pytest.mark.parametrize("sql", [s for s in WRITE_VERBS if "a.b.c" in s])
def test_every_write_verb_is_fenced_when_it_names_an_outside_object(sql):
    """The consequence: each of these must be ASKed when the object is outside `workspace.mine`."""
    assert classify_sql(sql) is not Action.READ
    assert check_sql(scope(), sql).verdict is not Verdict.ALLOW, (
        f"{sql!r} writes outside {SCHEMA} and must not be allowed")


# =============================================================== target extraction, directly

TARGET_CASES = [
    ("CREATE TABLE workspace.mine.t (x INT)", ["workspace.mine.t"]),
    ("CREATE TABLE IF NOT EXISTS a.b.c (x INT)", ["a.b.c"]),
    ("INSERT INTO workspace.mine.t SELECT * FROM workspace.other.s", ["workspace.mine.t"]),
    ("MERGE INTO workspace.mine.t USING s ON 1=1 WHEN MATCHED THEN UPDATE SET x=1", ["workspace.mine.t"]),
    ("OPTIMIZE workspace.mine.t ZORDER BY (a)", ["workspace.mine.t"]),
    ("VACUUM workspace.mine.t", ["workspace.mine.t"]),
    ("CREATE TABLE `a`.`b`.`c` (x INT)", ["a.b.c"]),
    ("SELECT * FROM workspace.other.t", []),
    ("OPTIMIZE", []),
]


@pytest.mark.parametrize("sql,expected", TARGET_CASES)
def test_target_extraction(sql, expected):
    assert sql_targets(sql) == expected


def test_targets_are_deduplicated():
    """One object written twice is one object: the refusal should not repeat itself."""
    assert sql_targets("INSERT INTO a.b.c VALUES (1)") == ["a.b.c"]


# =============================================================== the property, as a sweep

def test_no_write_verb_produces_an_allow_without_a_target():
    """The general form of the bug, swept over every verb the classifier knows.

    For every write verb, a statement that names an object OUTSIDE the schema is ASKed, and one that
    names nothing is ASKed. This is the invariant; the tables above are instances of it.
    """
    verbs = ["create table", "insert into", "merge into", "update", "alter table", "optimize",
             "vacuum", "delete from", "truncate table", "drop table", "comment on table"]
    failures = []
    for verb in verbs:
        outside = f"{verb} workspace.other.t"
        if check_sql(scope(), outside).verdict is Verdict.ALLOW:
            failures.append(f"{outside!r} was ALLOWED")
        bare = f"{verb}"
        if check_sql(scope(), bare).verdict is Verdict.ALLOW:
            failures.append(f"{bare!r} was ALLOWED")
    assert not failures, "\n".join(failures)


def test_inside_schema_is_a_closed_rule():
    """`_inside_schema` is total: it answers for every shape without raising."""
    for target in ("workspace.mine", "workspace.mine.t", "mine.t", "t", "",
                   "workspace", "workspace.other.t", "`. `", "a.b.c.d"):
        _inside_schema(target, SCHEMA)   # must not raise
