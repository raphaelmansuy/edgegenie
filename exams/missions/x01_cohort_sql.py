"""X1 (HELD-OUT) - Cohort retention matrix in SQL. Never used to tune any variant."""
from __future__ import annotations

from lib import Check, Ctx, Mission, sql, sql_val, table_exists

SEED = [
    """CREATE OR REPLACE TABLE {s}.signups AS
       SELECT id AS user_id, date_add(DATE'2026-08-03', CAST(pmod(hash(id,'s'),49) AS INT)) AS signup_date
       FROM range(600)""",
    """CREATE OR REPLACE TABLE {s}.activity AS
       WITH x AS (
         SELECT s.user_id, date_add(s.signup_date, d - 3) AS activity_date, d
         FROM {s}.signups s LATERAL VIEW explode(sequence(0, 38)) t AS d
         WHERE pmod(hash(s.user_id, d), 10) < 3)
       SELECT user_id, activity_date FROM x
       UNION ALL SELECT user_id, activity_date FROM x WHERE pmod(hash(user_id, d, 'dup'), 7) = 0""",
]

GOLDEN = """
WITH c AS (SELECT user_id, signup_date, CAST(date_trunc('week', signup_date) AS DATE) AS cohort_week FROM {s}.signups),
sz AS (SELECT cohort_week, count(*) AS cohort_size FROM c GROUP BY cohort_week),
a AS (SELECT c.cohort_week, CAST(floor(datediff(x.activity_date, c.signup_date) / 7) AS INT) AS week_n, c.user_id
      FROM c JOIN {s}.activity x ON x.user_id = c.user_id
      WHERE x.activity_date >= c.signup_date AND datediff(x.activity_date, c.signup_date) < 35),
r AS (SELECT cohort_week, week_n, count(DISTINCT user_id) AS active_users FROM a GROUP BY cohort_week, week_n)
SELECT sz.cohort_week, sz.cohort_size, w.week_n, coalesce(r.active_users, 0) AS active_users,
       round(100.0 * coalesce(r.active_users, 0) / sz.cohort_size, 1) AS retention_pct
FROM sz CROSS JOIN (SELECT explode(sequence(0, 4)) AS week_n) w
LEFT JOIN r ON r.cohort_week = sz.cohort_week AND r.week_n = w.week_n
"""
COLS = ("CAST(cohort_week AS DATE), CAST(cohort_size AS BIGINT), CAST(week_n AS INT), "
        "CAST(active_users AS BIGINT), CAST(retention_pct AS DOUBLE)")


def prompt(ctx: Ctx) -> str:
    return f"""Product wants a weekly retention matrix. We have {ctx.schema}.signups (user_id, signup_date) and {ctx.schema}.activity (user_id, activity_date; a user can have several rows per day and some rows are dated before the user signed up).

Build the table {ctx.schema}.x1_retention with columns, exactly: cohort_week, cohort_size, week_n, active_users, retention_pct.
- cohort_week = the Monday of the week of signup_date (a DATE). cohort_size = number of users who signed up in that week.
- week_n = whole weeks since the user's own signup_date: floor(days between signup_date and activity_date / 7). Only count week_n 0 to 4. Ignore activity dated before the user's signup_date.
- active_users = distinct users of the cohort with at least one activity in that week_n.
- retention_pct = 100 * active_users / cohort_size, rounded to 1 decimal.
- Every cohort has exactly 5 rows (week_n 0 to 4), including weeks with zero active users.

When done, reply with the SQL you used and the retention_pct of the earliest cohort for week_n = 2."""


def setup(ctx: Ctx) -> None:
    sql(f"CREATE SCHEMA IF NOT EXISTS {ctx.schema}")
    for q in SEED:
        sql(q.format(s=ctx.schema))


def reference(ctx: Ctx) -> str:
    g = GOLDEN.format(s=ctx.schema)
    sql(f"CREATE OR REPLACE TABLE {ctx.schema}.x1_retention AS {g}")
    v = sql_val(f"SELECT retention_pct FROM {ctx.schema}.x1_retention WHERE week_n = 2 ORDER BY cohort_week LIMIT 1")
    return f"SQL used: SELECT ... FROM signups JOIN activity ...\nEarliest cohort, week 2: {v}"


def grade(ctx: Ctx, answer: str) -> list[Check]:
    t = f"{ctx.schema}.x1_retention"
    if not table_exists(t):
        return [Check("result table exists", False, 3, f"{t} missing")]
    g = GOLDEN.format(s=ctx.schema)
    out = [Check("result table exists", True, 1)]
    cols = [r[0] for r in sql(f"SELECT column_name FROM {ctx.schema.split('.')[0]}.information_schema.columns "
                              f"WHERE table_schema='{ctx.schema_name}' AND table_name='x1_retention' ORDER BY ordinal_position")]
    want = ["cohort_week", "cohort_size", "week_n", "active_users", "retention_pct"]
    out.append(Check("columns exactly as specified", cols == want, 1, f"got {cols}"))
    got, gold = int(sql_val(f"SELECT count(*) FROM {t}") or 0), int(sql_val(f"SELECT count(*) FROM ({g})") or 0)
    out.append(Check("row count matches golden (5 rows per cohort)", got == gold, 1, f"got {got}, want {gold}"))
    if cols == want:
        diff = int(sql_val(f"SELECT count(*) FROM ((SELECT {COLS} FROM {t} EXCEPT SELECT {COLS} FROM ({g})) "
                           f"UNION ALL (SELECT {COLS} FROM ({g}) EXCEPT SELECT {COLS} FROM {t}))") or 0)
    else:
        diff = -1
    out.append(Check("every value equals golden (EXCEPT both ways)", diff == 0, 5, f"{diff} differing rows"))
    v = sql_val(f"SELECT retention_pct FROM ({g}) WHERE week_n = 2 ORDER BY cohort_week LIMIT 1")
    out.append(Check("answer reports the earliest cohort week-2 retention", bool(answer) and str(v) in answer, 1, f"want {v}"))
    return out


MISSION = Mission(
    id="X1", title="HELD-OUT: weekly cohort retention matrix", capability="C2", difficulty=3,
    prompt=prompt, setup=setup, grade=grade, reference=reference, cleanup=lambda ctx: None, max_minutes=10,
)
