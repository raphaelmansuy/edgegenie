"""Fail-closed Databricks SQL policy. Highlighting or a leading SELECT is not authorization."""

from __future__ import annotations

import datetime as dt
import re
from decimal import Decimal, InvalidOperation

from .sqlquery import SqlError

try:
    import sqlglot
    from sqlglot import exp
except ImportError:
    sqlglot = None

# A deliberate small initial function vocabulary. Unknown/UDF/external calls are refused.
FUNCTIONS = frozenset(
    {
        "COUNT",
        "SUM",
        "AVG",
        "MIN",
        "MAX",
        "COALESCE",
        "CAST",
        "TRY_CAST",
        "ABS",
        "ROUND",
        "LOWER",
        "UPPER",
        "LENGTH",
        "CONCAT",
        "SUBSTRING",
        "TRIM",
        "CURRENT_DATE",
        "CURRENT_TIMESTAMP",
        "DATE_TRUNC",
        "YEAR",
        "MONTH",
        "DAY",
        "ROW_NUMBER",
        "RANK",
        "DENSE_RANK",
        "LAG",
        "LEAD",
        "IF",
        "CASE",
    }
)
TYPE = re.compile(r"^(STRING|BIGINT|INT|INTEGER|DATE|TIMESTAMP|DECIMAL(?:\((\d{1,2}),(\d{1,2})\))?)$")


def available() -> bool:
    return sqlglot is not None


def validate(source: str, parameters: list[dict], *, dialect=None) -> list[dict]:
    if sqlglot is None:
        raise SqlError(
            "PARSER_UNAVAILABLE", "SQL execution is unavailable: the SQL parser must be installed.", 503
        )
    if not source.strip() or len(source.encode()) > 200 * 1024:
        raise SqlError("INVALID_SQL", "Enter one SQL query under 200 KiB.")
    try:
        # Bound nesting before invoking a recursive parser. Strings/comments are tokenized first.
        tokens = sqlglot.tokenize(source, read=dialect)
        if len(tokens) > 20000:
            raise ValueError("too many tokens")
        depth = 0
        for token in tokens:
            if token.text == "(":
                depth += 1
            elif token.text == ")":
                depth -= 1
            if depth > 64:
                raise ValueError("nesting exceeds 64 levels")
        parsed = [node for node in sqlglot.parse(source, read=dialect) if node is not None]
        if len(parsed) != 1 or not isinstance(
            parsed[0], (exp.Select, exp.Union, exp.Intersect, exp.Except)
        ):
            raise ValueError("only one read-only SELECT statement is supported")
        tree = parsed[0]
        for node in tree.walk():
            if isinstance(
                node, (exp.DDL, exp.DML, exp.Command, exp.Into, exp.Dot, exp.Lock, exp.Parameter)
            ):
                # Qualified columns also use Dot in some dialects; unsupported is safer than guessing.
                raise ValueError("unsupported or mutating SQL construct")
            if isinstance(node, exp.Func):
                name = node.name.upper() if isinstance(node, exp.Anonymous) else node.sql_name().upper()
                if name not in FUNCTIONS:
                    raise ValueError(f"function {name} is not in the supported read-only set")
        required = {str(p.this) for p in tree.find_all(exp.Placeholder)}
    except SqlError:
        raise
    except Exception as exc:
        raise SqlError(
            "INVALID_SQL",
            "Use one supported read-only SELECT. Scripts, mutations and unverified functions cannot run here.",
        ) from exc
    if len(parameters) > 100:
        raise SqlError("INVALID_PARAMETER", "At most 100 named parameters are supported.")
    bindings = {}
    for item in parameters:
        name = item.get("name", "")
        typ = str(item.get("type", "STRING")).upper()
        value = item.get("value")
        match = TYPE.fullmatch(typ)
        if not match or name in bindings or not re.fullmatch(r"[A-Za-z_]\w*", name):
            raise SqlError("INVALID_PARAMETER", "Parameter names must be unique and use supported types.")
        if value is not None:
            value = str(value)
            if len(value.encode()) > 16384:
                raise SqlError("INVALID_PARAMETER", f"Parameter {name} is too long.")
            try:
                if typ in {"INT", "INTEGER", "BIGINT"}:
                    number = int(value)
                    bits = 64 if typ == "BIGINT" else 32
                    if not -(2 ** (bits - 1)) <= number < 2 ** (bits - 1):
                        raise ValueError()
                elif typ.startswith("DECIMAL"):
                    number = Decimal(value)
                    if not number.is_finite():
                        raise ValueError()
                    if match[2]:
                        precision, scale = int(match[2]), int(match[3])
                        if (
                            not 0 <= scale <= precision <= 38
                            or number != number.quantize(Decimal(1).scaleb(-scale))
                            or abs(number) >= Decimal(10) ** (precision - scale)
                        ):
                            raise ValueError()
                elif typ == "DATE":
                    dt.date.fromisoformat(value)
                elif (
                    typ == "TIMESTAMP"
                    and dt.datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo is None
                ):
                    raise ValueError()
            except (ValueError, InvalidOperation) as exc:
                raise SqlError(
                    "INVALID_PARAMETER",
                    f"Parameter {name} is not a valid {typ}; timestamps require a timezone.",
                ) from exc
        bindings[name] = {"name": name, "type": typ, "value": value}
    if required != bindings.keys():
        raise SqlError("INVALID_PARAMETER", "Provide exactly the named parameters used by this query.")
    return list(bindings.values())
