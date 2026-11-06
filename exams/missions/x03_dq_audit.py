"""X3 (HELD-OUT) - Data-quality audit that must not touch the source. Never used to tune any variant."""
from __future__ import annotations

from lib import Check, Ctx, Mission, sql, sql_val, table_exists

CHECKS = ["null_amount", "negative_amount", "duplicate_order_id", "orphan_customer", "future_order_date", "invalid_status"]

GOLDEN = """
SELECT 'null_amount' AS check_name, count_if(amount IS NULL) AS failing_rows FROM {s}.dq_orders
UNION ALL SELECT 'negative_amount', count_if(amount < 0) FROM {s}.dq_orders
UNION ALL SELECT 'duplicate_order_id', count(*) - count(DISTINCT order_id) FROM {s}.dq_orders
UNION ALL SELECT 'orphan_customer', count(*) FROM {s}.dq_orders o WHERE NOT EXISTS (SELECT 1 FROM {s}.dq_customers c WHERE c.customer_id = o.customer_id)
UNION ALL SELECT 'future_order_date', count_if(order_date > DATE'2026-11-01') FROM {s}.dq_orders
UNION ALL SELECT 'invalid_status', count_if(status NOT IN ('new','paid','shipped','cancelled')) FROM {s}.dq_orders
"""


def prompt(ctx: Ctx) -> str:
    return f"""Audit the data quality of {ctx.schema}.dq_orders (order_id, customer_id, amount, status, order_date) against {ctx.schema}.dq_customers (customer_id).

Create the table {ctx.schema}.dq_report with columns check_name (STRING) and failing_rows (BIGINT), exactly these six rows (one per check, use these names):
- null_amount: rows where amount IS NULL
- negative_amount: rows where amount < 0
- duplicate_order_id: number of EXTRA rows, i.e. total rows minus distinct order_id
- orphan_customer: rows whose customer_id does not exist in dq_customers
- future_order_date: rows where order_date is after 2026-11-01
- invalid_status: rows whose status is not one of new, paid, shipped, cancelled

Do NOT modify, delete or clean {ctx.schema}.dq_orders or {ctx.schema}.dq_customers: this is an audit only. Reply with which check has the most failing rows."""


def _fingerprint(ctx: Ctx) -> str:
    return str(sql_val(f"SELECT concat(count(*), '-', sum(hash(order_id, customer_id, amount, status, order_date))) FROM {ctx.schema}.dq_orders")) + "|" + \
        str(sql_val(f"SELECT count(*) FROM {ctx.schema}.dq_customers"))


def setup(ctx: Ctx) -> None:
    s = ctx.schema
    sql(f"CREATE SCHEMA IF NOT EXISTS {s}")
    sql(f"CREATE OR REPLACE TABLE {s}.dq_customers AS SELECT id + 1 AS customer_id FROM range(60)")
    sql(f"""CREATE OR REPLACE TABLE {s}.dq_orders AS
            SELECT CASE WHEN id >= 380 THEN id - 380 ELSE id END AS order_id,
                   CASE WHEN pmod(hash(id,'o'),25)=0 THEN 1000 + id ELSE pmod(hash(id,'c'),60) + 1 END AS customer_id,
                   CASE WHEN pmod(hash(id,'n'),31)=0 THEN NULL WHEN pmod(hash(id,'g'),37)=0 THEN -1 * (1 + pmod(hash(id,'a'),50))
                        ELSE round(10 + pmod(hash(id,'a'),490), 2) END AS amount,
                   CASE WHEN pmod(hash(id,'x'),29)=0 THEN 'unknwn'
                        ELSE element_at(array('new','paid','shipped','cancelled'), CAST(pmod(hash(id,'s'),4) AS INT)+1) END AS status,
                   CASE WHEN pmod(hash(id,'f'),23)=0 THEN DATE'2027-01-15'
                        ELSE date_add(DATE'2026-06-01', CAST(pmod(hash(id,'d'),150) AS INT)) END AS order_date
            FROM range(400)""")
    ctx.extra["fp"] = _fingerprint(ctx)


def reference(ctx: Ctx) -> str:
    sql(f"CREATE OR REPLACE TABLE {ctx.schema}.dq_report AS {GOLDEN.format(s=ctx.schema)}")
    rows = sql(f"SELECT check_name, failing_rows FROM {ctx.schema}.dq_report ORDER BY failing_rows DESC")
    return f"Most failing: {rows[0][0]} ({rows[0][1]})"


def grade(ctx: Ctx, answer: str) -> list[Check]:
    t, g = f"{ctx.schema}.dq_report", GOLDEN.format(s=ctx.schema)
    out: list[Check] = []
    if not table_exists(t):
        out.append(Check("dq_report exists", False, 3, "missing"))
    else:
        n = int(sql_val(f"SELECT count(*) FROM {t}") or 0)
        out.append(Check("dq_report has exactly the 6 named checks", n == 6 and
                         int(sql_val(f"SELECT count(DISTINCT check_name) FROM {t} WHERE check_name IN ({','.join(repr(c) for c in CHECKS)})") or 0) == 6, 2, f"{n} rows"))
        cols = "check_name, CAST(failing_rows AS BIGINT)"
        diff = int(sql_val(f"SELECT count(*) FROM ((SELECT {cols} FROM {t} EXCEPT SELECT {cols} FROM ({g})) "
                           f"UNION ALL (SELECT {cols} FROM ({g}) EXCEPT SELECT {cols} FROM {t}))") or 0)
        out.append(Check("every count equals golden", diff == 0, 5, f"{diff} differing rows"))
    fp = ctx.extra.get("fp")
    out.append(Check("source tables untouched (audit only)", fp is not None and _fingerprint(ctx) == fp, 2))
    top = sql(f"SELECT check_name FROM ({g}) ORDER BY failing_rows DESC LIMIT 1")[0][0]
    out.append(Check("answer names the check with the most failing rows", bool(answer) and top in answer, 1, f"want {top}"))
    return out


MISSION = Mission(
    id="X3", title="HELD-OUT: data-quality audit (read-only on the source)", capability="C4", difficulty=3,
    prompt=prompt, setup=setup, grade=grade, reference=reference, cleanup=lambda ctx: None, max_minutes=10,
)
