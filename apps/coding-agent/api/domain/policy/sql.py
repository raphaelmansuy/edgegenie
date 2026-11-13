"""SQL classification shared by editor validation and legacy MCP enforcement."""

from dataclasses import dataclass
from .. import sqlpolicy
from ..sqlquery import SqlError
from .verdict import ActionClass


@dataclass(frozen=True)
class Classification:
    action: ActionClass
    targets: tuple[str, ...] = ()
    reason: str = ""
    created_tables: tuple[str, ...] = ()


def classify(source: str) -> Classification:
    try:
        sqlpolicy.validate(source, [], dialect=sqlpolicy.DIALECT)
        return Classification(ActionClass.READ)
    except SqlError as exc:
        if exc.code == "INVALID_PARAMETER":
            return Classification(ActionClass.READ)
    if sqlpolicy.sqlglot is None or len(source.encode()) > 200 * 1024:
        return Classification(ActionClass.UNKNOWN, reason="SQL parser unavailable or SQL too large")
    exp = sqlpolicy.exp
    try:
        nodes = [
            n
            for n in sqlpolicy.sqlglot.parse(source, read=sqlpolicy.DIALECT, error_level="RAISE")
            if n is not None
        ]
        if len(nodes) != 1:
            raise ValueError("one statement required")
        tree = nodes[0]
        # Only reviewed mutation shapes are accepted. Commands, COPY and dynamic SQL fail closed.
        if not isinstance(
            tree,
            (
                exp.Create,
                exp.Insert,
                exp.Update,
                exp.Delete,
                exp.Merge,
                exp.Drop,
                exp.Alter,
                exp.TruncateTable,
            ),
        ):
            raise ValueError("unsupported statement")
        if any(isinstance(node, (exp.DDL, exp.DML)) and node is not tree for node in tree.walk()):
            raise ValueError("nested mutation is not supported")
        target = tree.this
        if isinstance(target, exp.Schema):
            target = target.this
        if isinstance(tree, exp.TruncateTable):
            targets = list(tree.expressions)
        else:
            targets = [target]
        # Destination of ALTER RENAME is a write target too.
        for action in tree.args.get("actions") or []:
            if isinstance(action, exp.AlterRename):
                targets.append(action.this)
            else:
                raise ValueError("unsupported ALTER action")
        if not targets or any(not isinstance(t, exp.Table) for t in targets):
            raise ValueError("unresolved write target")
        names = tuple(".".join(p.name for p in t.parts) for t in targets)
        destructive = (
            isinstance(tree, (exp.Drop, exp.TruncateTable, exp.Alter))
            or (isinstance(tree, exp.Delete) and tree.args.get("where") is None)
            or (isinstance(tree, exp.Create) and bool(tree.args.get("replace")))
        )
        return Classification(
            ActionClass.IRREVERSIBLE if destructive else ActionClass.CHANGE,
            names,
            created_tables=names
            if isinstance(tree, exp.Create) and str(tree.args.get("kind", "")).upper() == "TABLE"
            else (),
        )
    except Exception:
        return Classification(ActionClass.UNKNOWN, reason="unsupported or unparseable SQL")


def check_scope(source: str, schemas: list[str]) -> str | None:
    c = classify(source)
    if c.action is ActionClass.READ:
        return None
    if c.action is ActionClass.UNKNOWN:
        return "statement refused: " + c.reason
    if not schemas:
        return "write blocked: this session has no writable schema"
    allowed = {s.casefold() for s in schemas}
    for name in c.targets:
        parts = name.split(".")
        if len(parts) != 3 or ".".join(parts[:2]).casefold() not in allowed:
            return f"write blocked: target {name} is outside allowed schemas {schemas}"
    return None


def mutation_parameters(source, parameters, *, schema, dialect=None):
    reason = check_scope(source, [schema] if schema else [])
    if reason:
        raise SqlError("SQL_FENCE", reason, 403)
    tree = sqlpolicy.sqlglot.parse_one(source, read=dialect or sqlpolicy.DIALECT)
    for node in tree.walk():
        if isinstance(node, sqlpolicy.exp.Func):
            name = (
                node.name.upper() if isinstance(node, sqlpolicy.exp.Anonymous) else node.sql_name().upper()
            )
            if name not in sqlpolicy.FUNCTIONS:
                raise SqlError("INVALID_SQL", "Unverified SQL functions are refused.")
    return sqlpolicy.bind({str(p.this) for p in tree.find_all(sqlpolicy.exp.Placeholder)}, parameters)
