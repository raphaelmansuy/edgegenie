"""M1 - Complex SQL (C2: write + execute SQL against governed data)."""
from __future__ import annotations

from lib import Check, Ctx, Mission, sql, sql_val, table_exists

# Golden query: window functions + a tie-broken mode + a running share.
GOLDEN = """
WITH base AS (
  SELECT pickup_zip, fare_amount, hour(tpep_pickup_datetime) AS hr
  FROM samples.nyctaxi.trips WHERE pickup_zip IS NOT NULL
),
zips AS (
  SELECT pickup_zip, count(*) AS trips, round(sum(fare_amount), 2) AS total_fare
  FROM base GROUP BY pickup_zip HAVING count(*) >= 200
),
hrs AS (
  SELECT pickup_zip, hr, count(*) AS c,
         row_number() OVER (PARTITION BY pickup_zip ORDER BY count(*) DESC, hr ASC) AS rn
  FROM base GROUP BY pickup_zip, hr
),
ranked AS (
  SELECT z.pickup_zip, z.trips, z.total_fare,
         dense_rank() OVER (ORDER BY z.total_fare DESC) AS fare_rank,
         round(100 * sum(z.total_fare) OVER (ORDER BY z.total_fare DESC, z.pickup_zip
               ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
               / sum(z.total_fare) OVER (), 2) AS cumulative_share_pct,
         h.hr AS busiest_hour
  FROM zips z JOIN hrs h ON h.pickup_zip = z.pickup_zip AND h.rn = 1
)
SELECT pickup_zip, trips, total_fare, fare_rank, cumulative_share_pct, busiest_hour
FROM ranked WHERE fare_rank <= 10
"""
COLS = "pickup_zip, trips, total_fare, fare_rank, cumulative_share_pct, busiest_hour"


def prompt(ctx: Ctx) -> str:
    return f"""Using the Unity Catalog table samples.nyctaxi.trips, build a ranking of the top pickup zip codes by revenue and save it as the table {ctx.schema}.m1_top_zips.

Rules for the result:
- Ignore trips where pickup_zip is NULL. Revenue is the sum of fare_amount.
- Only consider zips with at least 200 trips.
- Columns, exactly: pickup_zip, trips, total_fare (rounded to 2 decimals), fare_rank (DENSE_RANK by total_fare descending), cumulative_share_pct, busiest_hour.
- cumulative_share_pct = running sum of total_fare, ordered by total_fare descending then pickup_zip ascending, divided by the total revenue of all eligible zips, times 100, rounded to 2 decimals.
- busiest_hour = the hour of day (0-23, from tpep_pickup_datetime) with the most trips in that zip; break ties by choosing the smaller hour.
- Keep only rows with fare_rank <= 10.

When done, reply with the final SQL you used and the number of rows in the table."""


def setup(ctx: Ctx) -> None:
    sql(f"CREATE SCHEMA IF NOT EXISTS {ctx.schema}")


def reference(ctx: Ctx) -> str:
    sql(f"CREATE OR REPLACE TABLE {ctx.schema}.m1_top_zips AS {GOLDEN}")
    n = sql_val(f"SELECT count(*) FROM {ctx.schema}.m1_top_zips")
    return f"Final SQL used: {GOLDEN}\nRows: {n}"


def grade(ctx: Ctx, answer: str) -> list[Check]:
    t = f"{ctx.schema}.m1_top_zips"
    if not table_exists(t):
        return [Check("result table exists", False, 3, f"{t} missing")]
    out = [Check("result table exists", True, 1)]
    cols = [r[0] for r in sql(f"SELECT column_name FROM {ctx.schema.split('.')[0]}.information_schema.columns "
                              f"WHERE table_schema='{ctx.schema_name}' AND table_name='m1_top_zips' "
                              f"ORDER BY ordinal_position")]
    want = [c.strip() for c in COLS.split(",")]
    out.append(Check("columns exactly as specified", cols == want, 1, f"got {cols}"))
    got = int(sql_val(f"SELECT count(*) FROM {t}") or 0)
    gold = int(sql_val(f"SELECT count(*) FROM ({GOLDEN})") or 0)
    out.append(Check("row count matches golden", got == gold, 1, f"got {got}, want {gold}"))
    if cols == want:
        diff = int(sql_val(
            f"SELECT count(*) FROM ((SELECT {COLS} FROM {t} EXCEPT SELECT {COLS} FROM ({GOLDEN})) "
            f"UNION ALL (SELECT {COLS} FROM ({GOLDEN}) EXCEPT SELECT {COLS} FROM {t}))") or 0)
        out.append(Check("every value equals golden (EXCEPT both ways)", diff == 0, 4, f"{diff} differing rows"))
    else:
        out.append(Check("every value equals golden (EXCEPT both ways)", False, 4, "columns differ"))
    out.append(Check("answer reports SQL and row count", bool(answer) and str(gold) in answer
                     and "select" in answer.lower(), 1))
    return out


MISSION = Mission(
    id="M1", title="Complex SQL: windowed revenue ranking", capability="C2", difficulty=3,
    prompt=prompt, setup=setup, grade=grade, reference=reference,
    cleanup=lambda ctx: None, max_minutes=8,
)
