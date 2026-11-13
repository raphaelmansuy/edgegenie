"""The write fence: what a session may touch. Pure and total — every target is classified.

Policy adapters for legacy editor callers. Agent authorization uses the same pure policy package;
editor saves outside the working folder retain their explicit human approval flow.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

DESTRUCTIVE = re.compile(r"\b(drop\s+(table|schema|view|database)|truncate|delete\s+from)\b", re.I)
#: Verbs that change an object. `comment on` is here because it WRITES metadata: it was missing, so
#: `COMMENT ON TABLE someone_elses.table` was classified READ, allowed, and never reached the fence
#: at all. Found by `test_scope_targets.py::test_no_write_verb_produces_an_allow_without_a_target`,
#: which sweeps every verb rather than trusting a list of examples.
WRITE_SQL = re.compile(
    r"\b(create|replace|insert|update|merge|alter|optimize|vacuum|grant|revoke"
    r"|comment\s+on|undrop|restore|copy\s+into|refresh|analyze)\b",
    re.I,
)
# `_TABLE_RE` and `_FROM_RE` were the old target reader. They are gone: `_FROM_RE` matched sources as
# writes, and both together missed `OPTIMIZE`/`VACUUM` targets entirely. The reader now lives beside
# the rule that uses it (`_TARGETS` / `sql_targets` below), so the pattern and the fallback that
# covers what it cannot parse are read together.


class Action(str, Enum):
    READ = "read"
    WRITE = "write"
    DESTRUCTIVE = "destructive"
    RUN = "run"
    CREATE_APP = "create_app"


class Verdict(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class Scope:
    folder: str
    schema: str | None
    job_prefix: str
    app_prefix: str
    instance_prefix: str

    @staticmethod
    def for_session(session_id: str, folder: str, schema: str | None) -> Scope:
        """The fence for one conversation, derived through `fence_rules` so the empty case has ONE answer.

        Before this, `"/".rstrip("/") + "/"` was `"/"` — a prefix every absolute path matches — and the
        registry repeated the same arithmetic one layer down. `fence_rules.writable_folder` returns `""`
        for a root or an absent folder, and `""` is what both sides read as "no writable folder".
        """
        from .fence_rules import writable_folder

        short = session_id[:8]
        return Scope(
            folder=writable_folder(folder),
            schema=schema,
            job_prefix=f"agent_{short}_",
            app_prefix=f"agent-{short}-",
            instance_prefix=f"agent-{short}-",
        )


@dataclass(frozen=True, slots=True)
class Decision:
    verdict: Verdict
    action: Action
    target: str
    reason: str = ""

    @property
    def allowed(self) -> bool:
        return self.verdict is Verdict.ALLOW


# Compatibility exports for editor callers; implementation lives in one policy module.
from .policy.paths import inside as _inside, normalize as _norm


def classify_sql(sql: str) -> Action:
    if DESTRUCTIVE.search(sql) or re.search(r"\bcreate\s+or\s+replace\b", sql, re.I):
        return Action.DESTRUCTIVE
    if WRITE_SQL.search(sql):
        return Action.WRITE
    return Action.READ


# -- write targets, and the rule that a write we cannot place is not a write we may allow ---------
#
# `sql_targets` used to be `_TABLE_RE.findall(sql) + _FROM_RE.findall(sql)`. Two defects, both found
# by writing the table in `tests/test_scope_targets.py`:
#
#   1. `FROM` made a *source* a target. `INSERT INTO mine.t SELECT * FROM other.s` produced two
#      targets, so a write correctly inside the schema was ASKed because it also read a table —
#      and reading is deliberately free. The tool server already scoped this correctly (it matches
#      write targets only); the app was the side that was wrong.
#   2. Worse, the `FROM` alternative matched `FROM` on its own, so any write whose verb was not
#      followed by a name it recognised produced NO targets and fell through to `ALLOW`:
#      `OPTIMIZE <anything>`, `VACUUM <anything>`. Measured: `check_sql(scope, "OPTIMIZE
#      workspace.other.t")` answered ALLOW for a table outside the fence.
#
# The fix is two things, not one. A target reader that looks only at write verbs, AND an explicit
# rule that a write with no identifiable target is ASKed. A pattern alone cannot be trusted to
# place every statement — dialects differ, and `OPTIMIZE ... ZORDER BY (...)` has no "TABLE"
# keyword — so the fallback is the guarantee, exactly as the tool server's own
# `_check_sql_scope` refuses when it cannot identify a target.

_ID = r"`?[A-Za-z_][\w\-$]*`?"
#: The `catalog.schema.table` shape, 1 to 3 parts. A bare name is kept as one part so the caller can
#: decide that it cannot be placed (it is relative to whatever default schema the warehouse holds).
_NAME = rf"({_ID})(?:\.({_ID}))?(?:\.({_ID}))?"
_TARGETS = re.compile(
    r"(?i)\b(?:"
    r"create\s+(?:or\s+replace\s+)?(?:temp(?:orary)?\s+)?(?:external\s+)?"
    r"(?:table|view|materialized\s+view|streaming\s+table|schema|volume|function|database)"
    r"(?:\s+if\s+not\s+exists)?"
    r"|insert\s+(?:into|overwrite)(?:\s+table)?"
    r"|merge\s+into|update|delete\s+from|truncate\s+table|copy\s+into"
    r"|drop\s+(?:table|view|schema|volume|function|database)(?:\s+if\s+exists)?"
    r"|alter\s+(?:table|view|schema|database|volume)"
    r"|comment\s+on\s+(?:table|schema|column)"
    r"|optimize|vacuum|undrop|restore|refresh|analyze"
    r")\s+" + _NAME
)

#: Words that can follow a write verb but are part of the statement, not an object name.
#: `MERGE INTO t USING s ON … WHEN MATCHED THEN UPDATE SET x=1` matched `UPDATE SET`, so `SET`
#: appeared as a target and the refusal named it — true that the statement needs a human, but the
#: reason pointed at a word. A name in this set is dropped.
_NOT_A_NAME = frozenset({
    "set", "where", "select", "values", "if", "table", "view", "schema", "database", "volume",
    "function", "into", "from", "as", "on", "using", "when", "then", "and", "or", "not", "with",
    "by", "order", "group", "limit", "all", "distinct", "retain", "zorder", "cluster", "exists",
})


def sql_targets(sql: str) -> list[str]:
    """The objects a statement WRITES, fully qualified where the statement says so.

    Write targets only. A CTAS's `FROM` is a read and is not returned: reads are not fenced, and
    including them made a correctly-scoped write look out of scope. A name is returned as written
    (backticks stripped), so a two-part name is a two-part name and the caller decides whether it can
    be placed inside the session's three-part schema.
    """
    out: list[str] = []
    for parts in _TARGETS.findall(sql):
        pieces = [p.strip("`\"") for p in parts if p]
        if not pieces or pieces[0].lower() in _NOT_A_NAME:
            continue
        name = ".".join(pieces)
        if name and name.lower() not in {o.lower() for o in out}:
            out.append(name)
    return out


def _inside_schema(target: str, schema: str) -> bool:
    """Is `target` the schema itself, or an object in it?

    The session's schema is what the agent may write. A target qualifies when it is **at least as
    qualified as the schema** and its leading parts match:

        schema   = workspace.mine
        target   = workspace.mine         the schema itself          -> inside
        target   = workspace.mine.t       a table in it              -> inside
        target   = workspace.mine.a.b     a column, or a deeper name -> inside
        target   = workspace.other.t      a different schema         -> outside
        target   = mine.t                 a DIFFERENT catalog's "mine.mine.t"?  -> outside (unprovable)
        target   = t                      a default-schema object    -> outside (unprovable)

    A shorter target is refused even when its parts look equal, because `mine.t` under a three-part
    schema is ambiguous: it could be the current catalog's `mine` schema, or another one's. The app
    does not control the warehouse's default catalog, so it cannot resolve it, and guessing is the
    failure mode this fence exists to prevent.
    """
    t = target.strip("`\"").lower()
    s = schema.strip("`\"").lower()
    if not t or not s:
        return False
    parts, schema_parts = t.split("."), s.split(".")
    if len(parts) < len(schema_parts):
        return False
    return parts[:len(schema_parts)] == schema_parts


def check_sql(scope: Scope, sql: str) -> Decision:
    """Classify one statement, and say what may happen to it.

    The order is the specification, and the fallback is the safety property:

      1. destructive  -> ASK, always, wherever it points
      2. a read       -> ALLOW; Unity Catalog still decides what this user may see
      3. no writable schema, or no identifiable target -> ASK
      4. any target not placeable inside the schema   -> ASK
      5. otherwise    -> ALLOW
    """
    action = classify_sql(sql)
    if action is Action.READ:
        return Decision(Verdict.ALLOW, Action.READ, "")
    if action is Action.DESTRUCTIVE:
        return Decision(
            Verdict.ASK,
            Action.DESTRUCTIVE,
            " ".join(sql.split())[:160],
            "destructive SQL always needs a human",
        )
    targets = sql_targets(sql)
    if not scope.schema:
        return Decision(
            Verdict.ASK, action, ", ".join(targets)[:160], "this session has no writable schema"
        )
    if not targets:
        # A write this classifier cannot place. `OPTIMIZE`/`VACUUM`/`RESTORE` reach here against a
        # table name the pattern did not capture, and the honest answer is a human, not silence.
        return Decision(
            Verdict.ASK,
            action,
            " ".join(sql.split())[:160],
            "this write's target could not be identified, so it cannot be placed inside the fence",
        )
    outside = [t for t in targets if not _inside_schema(t, scope.schema)]
    if outside:
        return Decision(
            Verdict.ASK, action, ", ".join(outside)[:160], f"outside the writable schema {scope.schema}"
        )
    return Decision(Verdict.ALLOW, action, ", ".join(targets)[:160])


def check_path(scope: Scope, path: str) -> Decision:
    if _inside(path, scope.folder):
        return Decision(Verdict.ALLOW, Action.WRITE, _norm(path))
    reason = (f"outside {scope.folder}" if scope.folder
              else "no session is open, so there is no working folder to save into")
    return Decision(Verdict.ASK, Action.WRITE, _norm(path)[:160], reason)


def check_job(scope: Scope, name: str) -> Decision:
    if name.startswith(scope.job_prefix):
        return Decision(Verdict.ALLOW, Action.RUN, name)
    return Decision(
        Verdict.ASK, Action.RUN, name[:160], f"job names in this session start with {scope.job_prefix}"
    )


def check_app(scope: Scope, name: str) -> Decision:
    if name.startswith(scope.app_prefix):
        return Decision(Verdict.ALLOW, Action.CREATE_APP, name)
    return Decision(
        Verdict.ASK,
        Action.CREATE_APP,
        name[:160],
        f"app names in this session start with {scope.app_prefix}",
    )


def check_instance(scope: Scope, name: str) -> Decision:
    if name.startswith(scope.instance_prefix):
        return Decision(Verdict.ALLOW, Action.WRITE, name)
    return Decision(
        Verdict.ASK,
        Action.WRITE,
        name[:160],
        f"instance names in this session start with {scope.instance_prefix}",
    )


def describe(scope: Scope) -> dict:
    return {
        "folder": scope.folder,
        "schema": scope.schema,
        "jobPrefix": scope.job_prefix,
        "appPrefix": scope.app_prefix,
        "instancePrefix": scope.instance_prefix,
    }
