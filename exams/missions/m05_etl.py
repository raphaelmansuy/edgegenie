"""M5 - Build an ETL pipeline as a Databricks Job and run it (C7: pipelines & jobs)."""
from __future__ import annotations

import base64
import time

from lib import (Check, Ctx, Mission, api, delete_path, find_jobs, import_nb, latest_run,
                 mkdirs, sql, sql_val, table_exists)

SEED = """
CREATE OR REPLACE TABLE {s}.raw_events AS
WITH e AS (
  SELECT id,
         concat('e', id) AS event_id,
         CASE WHEN pmod(hash(id, 'u'), 100) < 5 THEN NULL
              ELSE concat('u', CAST(pmod(hash(id, 'user'), 300) AS STRING)) END AS user_id,
         CASE WHEN pmod(hash(id, 'b'), 100) < 3 THEN 'N/A'
              ELSE date_format(timestampadd(SECOND, CAST(pmod(hash(id,'t'), 86400) AS INT),
                   CAST(date_add(DATE'2026-10-01', CAST(id % 14 AS INT)) AS TIMESTAMP)), 'yyyy-MM-dd HH:mm:ss') END AS event_ts,
         CASE pmod(hash(id, 'ty'), 4) WHEN 0 THEN 'purchase' WHEN 1 THEN 'view' WHEN 2 THEN 'click' ELSE 'purchase' END AS event_type,
         round(5 + pmod(hash(id, 'a'), 9500) / 100.0, 2) AS raw_amount
  FROM range(0, 3000)
),
v1 AS (
  SELECT event_id, user_id, event_ts, event_type,
         CASE WHEN event_type = 'purchase' THEN raw_amount END AS amount,
         TIMESTAMP'2026-10-20 00:00:00' AS ingested_at FROM e
),
v2 AS (
  SELECT event_id, user_id, event_ts, event_type,
         CASE WHEN event_type = 'purchase' THEN raw_amount + 1.0 END AS amount,
         TIMESTAMP'2026-10-21 00:00:00' AS ingested_at
  FROM e WHERE pmod(hash(id, 'd'), 10) = 0
)
SELECT * FROM v1 UNION ALL SELECT * FROM v2
"""

LATEST = "SELECT * FROM (SELECT *, row_number() OVER (PARTITION BY event_id ORDER BY ingested_at DESC) rn FROM {s}.raw_events) WHERE rn = 1"
PARSED = "SELECT event_id, user_id, try_to_timestamp(event_ts) AS ts, event_ts AS raw_ts, event_type, amount FROM ({latest})"
G_SILVER = ("SELECT event_id, user_id, ts AS event_ts, event_type, CAST(amount AS DOUBLE) AS amount "
            "FROM ({parsed}) WHERE user_id IS NOT NULL AND ts IS NOT NULL")
G_REJECT = ("SELECT event_id, CASE WHEN user_id IS NULL THEN 'null_user_id' ELSE 'bad_timestamp' END AS reject_reason "
            "FROM ({parsed}) WHERE user_id IS NULL OR ts IS NULL")
G_GOLD = ("SELECT to_date(event_ts) AS event_date, count(DISTINCT user_id) AS active_users, "
          "count_if(event_type = 'purchase') AS purchases, "
          "round(coalesce(sum(CASE WHEN event_type = 'purchase' THEN amount END), 0), 2) AS revenue "
          "FROM silver GROUP BY 1")


def golden(ctx: Ctx) -> dict[str, str]:
    latest = LATEST.format(s=ctx.schema)
    parsed = PARSED.format(latest=latest)
    silver = G_SILVER.format(parsed=parsed)
    return {
        "silver_events": silver,
        "silver_rejects": G_REJECT.format(parsed=parsed),
        "gold_daily": f"WITH silver AS ({silver}) {G_GOLD}",
    }


def job_name(ctx: Ctx) -> str:
    return ctx.extra.get("jobPrefix", f"{ctx.run_id}_") + "etl"


def prompt(ctx: Ctx) -> str:
    return f"""Build a small medallion ETL pipeline over the raw table {ctx.schema}.raw_events (columns: event_id, user_id, event_ts as STRING, event_type, amount, ingested_at). Known problems in the raw data: the same event_id can appear more than once (a later ingested_at is a correction), some user_id are NULL, and some event_ts are not parseable timestamps (e.g. 'N/A').

Produce these Unity Catalog tables in the schema {ctx.schema}:
1. silver_events (event_id, user_id, event_ts TIMESTAMP, event_type, amount DOUBLE): FIRST keep one row per event_id (the row with the latest ingested_at), THEN keep only rows with a non-NULL user_id and a parseable event_ts.
2. silver_rejects (event_id, reject_reason): the de-duplicated rows that were excluded from silver, with reject_reason = 'null_user_id' (checked first) or 'bad_timestamp'.
3. gold_daily (event_date DATE, active_users = distinct user_id, purchases = number of event_type 'purchase' rows, revenue = sum(amount) of purchases rounded to 2 decimals, 0 if none), derived from silver_events.

Orchestration requirements:
- Implement it as a Databricks Job named exactly {job_name(ctx)} with at least two tasks (a silver task, and a gold task that depends on it). Notebook tasks stored under {ctx.home}/m5_etl/ running on serverless compute are fine.
- The job must be idempotent: running it twice must give identical tables (no double counting).
- Run the job at least once, wait for it to succeed, and report the job id, the run id, and the row count of each table."""


def setup(ctx: Ctx) -> None:
    sql(f"CREATE SCHEMA IF NOT EXISTS {ctx.schema}")
    sql(SEED.format(s=ctx.schema))
    mkdirs(f"{ctx.home}/m5_etl")


def _wait_run(run_id: int, timeout: int = 600) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        d = api("GET", "/api/2.1/jobs/runs/get", params={"run_id": run_id})
        if d["state"]["life_cycle_state"] in ("TERMINATED", "SKIPPED", "INTERNAL_ERROR"):
            return d
        time.sleep(6)
    return d


def reference(ctx: Ctx) -> str:
    g = golden(ctx)
    s = ctx.schema
    import_nb(f"{ctx.home}/m5_etl/silver", f'''# Databricks notebook source
spark.sql("""CREATE OR REPLACE TABLE {s}.silver_events AS {g["silver_events"]}""")
spark.sql("""CREATE OR REPLACE TABLE {s}.silver_rejects AS {g["silver_rejects"]}""")
''')
    import_nb(f"{ctx.home}/m5_etl/gold", f'''# Databricks notebook source
spark.sql("""CREATE OR REPLACE TABLE {s}.gold_daily AS
WITH silver AS (SELECT * FROM {s}.silver_events) {G_GOLD}""")
''')
    jid = api("POST", "/api/2.1/jobs/create", {
        "name": job_name(ctx),
        "tasks": [
            {"task_key": "silver", "notebook_task": {"notebook_path": f"{ctx.home}/m5_etl/silver"}},
            {"task_key": "gold", "depends_on": [{"task_key": "silver"}],
             "notebook_task": {"notebook_path": f"{ctx.home}/m5_etl/gold"}},
        ]})["job_id"]
    rid = api("POST", "/api/2.1/jobs/run-now", {"job_id": jid})["run_id"]
    _wait_run(rid)
    counts = {t: sql_val(f"SELECT count(*) FROM {s}.{t}") for t in golden(ctx)}
    return f"job_id={jid} run_id={rid} counts={counts}"


def _diff(ctx: Ctx, table: str, gold_sql: str, cols: str) -> int:
    t = f"{ctx.schema}.{table}"
    return int(sql_val(
        f"SELECT count(*) FROM ((SELECT {cols} FROM {t} EXCEPT SELECT {cols} FROM ({gold_sql})) "
        f"UNION ALL (SELECT {cols} FROM ({gold_sql}) EXCEPT SELECT {cols} FROM {t}))") or 0)


def grade(ctx: Ctx, answer: str) -> list[Check]:
    g = golden(ctx)
    out: list[Check] = []
    cols = {
        "silver_events": "event_id, user_id, CAST(event_ts AS TIMESTAMP), event_type, CAST(amount AS DOUBLE)",
        "silver_rejects": "event_id, reject_reason",
        "gold_daily": "CAST(event_date AS DATE), CAST(active_users AS BIGINT), CAST(purchases AS BIGINT), CAST(revenue AS DOUBLE)",
    }
    weights = {"silver_events": 4, "silver_rejects": 2, "gold_daily": 3}
    for t, w in weights.items():
        full = f"{ctx.schema}.{t}"
        if not table_exists(full):
            out.append(Check(f"{t} equals golden", False, w, "missing"))
            continue
        try:
            n = _diff(ctx, t, g[t], cols[t])
            out.append(Check(f"{t} equals golden (EXCEPT both ways)", n == 0, w, f"{n} differing rows"))
        except Exception as e:  # noqa: BLE001
            out.append(Check(f"{t} equals golden", False, w, str(e)[:200]))
    jobs = find_jobs(job_name(ctx))
    exact = [j for j in jobs if j["settings"]["name"] == job_name(ctx)]
    out.append(Check(f"job named {job_name(ctx)} exists", bool(exact), 1))
    if not exact:
        out += [Check("job has >= 2 tasks with a dependency", False, 1),
                Check("latest run succeeded", False, 2), Check("re-running the job is idempotent", False, 2)]
        return out
    job = exact[0]
    full = api("GET", "/api/2.1/jobs/get", params={"job_id": job["job_id"]})
    tasks = full["settings"].get("tasks", [])
    out.append(Check("job has >= 2 tasks with a dependency",
                     len(tasks) >= 2 and any(t.get("depends_on") for t in tasks), 1, f"{len(tasks)} tasks"))
    lr = latest_run(job["job_id"])
    out.append(Check("latest run succeeded", bool(lr) and lr["state"].get("result_state") == "SUCCESS", 2,
                     str(lr and lr["state"])))
    # idempotency: snapshot counts, re-run, compare
    before = {t: sql_val(f"SELECT count(*) FROM {ctx.schema}.{t}") for t in weights if table_exists(f"{ctx.schema}.{t}")}
    ok = False
    try:
        rid = api("POST", "/api/2.1/jobs/run-now", {"job_id": job["job_id"]})["run_id"]
        d = _wait_run(rid)
        after = {t: sql_val(f"SELECT count(*) FROM {ctx.schema}.{t}") for t in before}
        ok = d["state"].get("result_state") == "SUCCESS" and after == before
        detail = f"before={before} after={after} state={d['state'].get('result_state')}"
    except Exception as e:  # noqa: BLE001
        detail = str(e)[:200]
    out.append(Check("grader re-runs the job: still succeeds and counts unchanged (idempotent)", ok, 2, detail))
    return out


def cleanup(ctx: Ctx) -> None:
    for j in find_jobs(job_name(ctx)):
        try:
            api("POST", "/api/2.1/jobs/delete", {"job_id": j["job_id"]})
        except RuntimeError:
            pass


MISSION = Mission(
    id="M5", title="ETL pipeline: medallion job, idempotent, scheduled run", capability="C7", difficulty=4,
    prompt=prompt, setup=setup, grade=grade, reference=reference, cleanup=cleanup, max_minutes=15,
)
