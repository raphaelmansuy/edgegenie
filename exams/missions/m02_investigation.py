"""M2 - Data investigation (C4: diagnose a data problem from evidence)."""
from __future__ import annotations

import re

from lib import Check, Ctx, Mission, sql, sql_val

ANOMALY_DATE = "2026-09-10"

SEED = """
CREATE OR REPLACE TABLE {s}.orders AS
WITH base AS (
  SELECT id AS order_id,
         date_add(DATE'2026-08-01', CAST(id % 60 AS INT)) AS d,
         CAST(pmod(hash(id, 't'), 86400) AS INT) AS secs,
         CAST(pmod(hash(id, 'k'), 900) AS INT) + 1 AS customer_id,
         CASE WHEN pmod(hash(id, 'c'), 10) < 5 THEN 'USD'
              WHEN pmod(hash(id, 'c'), 10) < 8 THEN 'EUR' ELSE 'GBP' END AS currency,
         round(10 + pmod(hash(id, 'a'), 19000) / 100.0, 2) AS base_amount,
         CASE pmod(hash(id, 'ch'), 3) WHEN 0 THEN 'web' WHEN 1 THEN 'ios' ELSE 'android' END AS channel
  FROM range(0, 6000)
),
orders AS (
  SELECT order_id, timestampadd(SECOND, secs, CAST(d AS TIMESTAMP)) AS order_ts, customer_id, currency,
         CASE WHEN currency = 'EUR' AND d >= DATE'{anomaly}' THEN round(base_amount * 100, 2)
              ELSE base_amount END AS amount, channel
  FROM base
)
SELECT * FROM orders
UNION ALL
SELECT * FROM (SELECT * FROM orders WHERE to_date(order_ts) = DATE'2026-08-20' LIMIT 40)
"""


def setup(ctx: Ctx) -> None:
    sql(f"CREATE SCHEMA IF NOT EXISTS {ctx.schema}")
    sql(SEED.format(s=ctx.schema, anomaly=ANOMALY_DATE))
    ctx.extra["fingerprint"] = sql(f"SELECT count(*), round(sum(amount),2) FROM {ctx.schema}.orders")[0]


def prompt(ctx: Ctx) -> str:
    return f"""The finance dashboard that reads {ctx.schema}.orders (one row per order; amount is the order value in the order's own currency) shows daily revenue jumping to many times its usual level partway through the period covered by the table. Nobody has deployed anything that should explain it.

Investigate with queries and find the root cause. This is READ-ONLY: do not modify, delete or recreate any data.

Your final answer must state:
1. the exact date the problem starts,
2. which segment(s) of the data are affected (and which are not),
3. what is wrong with the values (be specific and quantify it with numbers from the data),
4. one recommended fix.
Support each claim with the query result that proves it. Also mention anything else odd you noticed that is NOT the cause of the jump."""


def reference(ctx: Ctx) -> str:
    return (f"The jump starts on {ANOMALY_DATE}. Only currency = EUR is affected; USD and GBP are unchanged. "
            "From that date EUR amounts are exactly 100x larger than before, which means they are being "
            "stored in cents (minor units) instead of euros: EUR average amount is about 105 before and "
            "about 10,500 after. Fix: divide EUR amounts by 100 from that date in the ingestion and backfill. "
            "Separately, 2026-08-20 contains 40 duplicated order_id rows, which is a minor issue and not the cause.")


def grade(ctx: Ctx, answer: str) -> list[Check]:
    fp = sql(f"SELECT count(*), round(sum(amount),2) FROM {ctx.schema}.orders")[0]
    unchanged = fp == ctx.extra.get("fingerprint", fp)
    a = answer or ""
    date_ok = bool(re.search(r"2026-09-10|sep(?:tember)?\s*10", a, re.I))
    cur_ok = bool(re.search(r"\bEUR\b|euro", a, re.I))
    only_eur = cur_ok and bool(re.search(r"(usd|gbp)[^.]{0,80}(unaffected|not affected|normal|unchanged|fine|stable)|"
                                         r"(only|just)[^.]{0,40}eur", a, re.I))
    unit_ok = bool(re.search(r"cents?|minor unit|100\s*x|x\s*100|100 times|factor of 100|100-fold|hundred", a, re.I))
    quant_ok = bool(re.search(r"\b(1[0-9]{2}|[0-9]{2})(\.\d+)?\b.{0,80}\b(1[0-9],?[0-9]{3}|[0-9],?[0-9]{3})(\.\d+)?\b", a, re.S)) \
        and unit_ok
    fix_ok = bool(re.search(r"divid|/\s*100|backfill|correct|convert|fix", a, re.I))
    mentions_dupes = bool(re.search(r"duplicate|duplicated|2026-08-20|aug(?:ust)?\s*20", a, re.I))
    wrong_cause = bool(re.search(r"(root cause|caused by)[^.]{0,80}(duplicate|promotion|seasonal|bot)", a, re.I))
    return [
        Check("read-only: table unchanged", unchanged, 2, f"fingerprint {fp}"),
        Check("exact start date 2026-09-10", date_ok, 2),
        Check("identifies EUR as the affected segment", cur_ok, 2),
        Check("states other currencies are unaffected", only_eur, 1),
        Check("diagnoses unit error (cents / 100x)", unit_ok, 3),
        Check("quantifies with numbers", quant_ok, 1),
        Check("recommends a concrete fix", fix_ok, 1),
        Check("notices the unrelated duplicates (distractor) without blaming them",
              mentions_dupes and not wrong_cause, 1),
    ]


MISSION = Mission(
    id="M2", title="Data investigation: why did revenue jump?", capability="C4", difficulty=3,
    prompt=prompt, setup=setup, grade=grade, reference=reference, max_minutes=8,
)
