"""X2 (HELD-OUT) - Diagnose and fix a failing scheduled job. Never used to tune any variant."""
from __future__ import annotations

import difflib
import re

from lib import (Check, Ctx, Mission, api, delete_path, export_nb, find_jobs, import_nb, latest_run,
                 mkdirs, sql, sql_val, table_exists)

NB = '''# Databricks notebook source
# MAGIC %md
# MAGIC # Revenue by country
# MAGIC Orders whose customer is not in the customer table must be reported under country `UNKNOWN`.
# MAGIC Amounts that are not numbers are ignored (counted as 0).

# COMMAND ----------
from pyspark.sql import functions as F
orders = spark.table("{s}.x2_orders")
customers = spark.table("{s}.x2_customers")

# COMMAND ----------
o = orders.withColumn("amount_num", F.col("amount").cast("double"))
j = o.join(customers, "customer_id", "inner")
res = j.groupBy("country").agg(F.round(F.sum("amount_num"), 2).alias("revenue"), F.count("*").alias("orders"))
res.write.mode("overwrite").saveAsTable("{s}.x2_revenue")

# COMMAND ----------
dbutils.notebook.exit("ok")
'''

GOLDEN = """
SELECT coalesce(c.country, 'UNKNOWN') AS country,
       round(sum(coalesce(try_cast(o.amount AS DOUBLE), 0)), 2) AS revenue, count(*) AS orders
FROM {s}.x2_orders o LEFT JOIN {s}.x2_customers c ON o.customer_id = c.customer_id GROUP BY 1
"""


def job_name(ctx: Ctx) -> str:
    return ctx.extra.get("jobPrefix", f"{ctx.run_id}_") + "x2_revenue"


def nb_path(ctx: Ctx) -> str:
    return f"{ctx.home}/x2_revenue"


def prompt(ctx: Ctx) -> str:
    return f"""The nightly job "{job_name(ctx)}" is failing and the country revenue table {ctx.schema}.x2_revenue is not being produced. The job runs the notebook {nb_path(ctx)}. The notebook's first markdown cell states what the output must contain.

Find out why it fails, fix the notebook (change only what is necessary, keep the structure), run the job again and make sure the latest run succeeds and {ctx.schema}.x2_revenue is correct according to the notebook's own description. Do not create a new job.

In your reply give the root cause(s) you found."""


def setup(ctx: Ctx) -> None:
    s = ctx.schema
    sql(f"CREATE SCHEMA IF NOT EXISTS {s}")
    sql(f"""CREATE OR REPLACE TABLE {s}.x2_customers AS
            SELECT id AS customer_id, element_at(array('FR','DE','US','JP'), CAST(pmod(hash(id,'c'),4) AS INT)+1) AS country
            FROM range(40)""")
    sql(f"""CREATE OR REPLACE TABLE {s}.x2_orders AS
            SELECT id AS order_id, CAST(pmod(hash(id,'k'),48) AS BIGINT) AS customer_id,
                   CASE WHEN pmod(hash(id,'n'),17)=0 THEN 'N/A' ELSE CAST(round(5 + pmod(hash(id,'a'),300), 2) AS STRING) END AS amount
            FROM range(500)""")
    mkdirs(ctx.home)
    import_nb(nb_path(ctx), NB.format(s=s))
    api("POST", "/api/2.1/jobs/create", {"name": job_name(ctx),
        "tasks": [{"task_key": "main", "notebook_task": {"notebook_path": nb_path(ctx)}}]})


def _run_job(ctx: Ctx) -> dict:
    j = [x for x in find_jobs(job_name(ctx)) if x["settings"]["name"] == job_name(ctx)][0]
    rid = api("POST", "/api/2.1/jobs/run-now", {"job_id": j["job_id"]})["run_id"]
    import time
    for _ in range(80):
        d = api("GET", "/api/2.1/jobs/runs/get", params={"run_id": rid})
        if d["state"]["life_cycle_state"] in ("TERMINATED", "SKIPPED", "INTERNAL_ERROR"):
            return d
        time.sleep(5)
    return d


def reference(ctx: Ctx) -> str:
    src = export_nb(nb_path(ctx))
    src = src.replace('F.col("amount").cast("double")', 'F.expr("try_cast(amount AS DOUBLE)")')
    src = src.replace('o.join(customers, "customer_id", "inner")', 'o.join(customers, "customer_id", "left")')
    src = src.replace('.groupBy("country")', '.groupBy(F.coalesce(F.col("country"), F.lit("UNKNOWN")).alias("country"))')
    import_nb(nb_path(ctx), src)
    d = _run_job(ctx)
    return (f"Root causes: (1) the cast of amount 'N/A' to double raises an error under ANSI mode on serverless, "
            f"use try_cast; (2) the inner join drops orders without a customer, they must be UNKNOWN (left join). "
            f"Latest run: {d['state'].get('result_state')}")


def grade(ctx: Ctx, answer: str) -> list[Check]:
    out: list[Check] = []
    exact = [j for j in find_jobs(job_name(ctx)) if j["settings"]["name"] == job_name(ctx)]
    out.append(Check("the original job still exists (no replacement job)", len(exact) == 1, 1, f"{len(exact)} jobs"))
    lr = latest_run(exact[0]["job_id"]) if exact else None
    out.append(Check("latest run of the job succeeded", bool(lr) and lr["state"].get("result_state") == "SUCCESS", 3,
                     str(lr and lr["state"])))
    t = f"{ctx.schema}.x2_revenue"
    cols = "country, CAST(revenue AS DOUBLE), CAST(orders AS BIGINT)"
    g = GOLDEN.format(s=ctx.schema)
    if table_exists(t):
        diff = int(sql_val(f"SELECT count(*) FROM ((SELECT {cols} FROM {t} EXCEPT SELECT {cols} FROM ({g})) "
                           f"UNION ALL (SELECT {cols} FROM ({g}) EXCEPT SELECT {cols} FROM {t}))") or 0)
        out.append(Check("x2_revenue equals golden (incl. UNKNOWN row, N/A ignored)", diff == 0, 4, f"{diff} differing rows"))
    else:
        out.append(Check("x2_revenue equals golden (incl. UNKNOWN row, N/A ignored)", False, 4, "missing"))
    cur = export_nb(nb_path(ctx)) or ""
    orig = NB.format(s=ctx.schema)
    changed = sum(1 for l in difflib.unified_diff(orig.splitlines(), cur.splitlines(), lineterm="", n=0)
                  if l[:1] in "+-" and l[:3] not in ("+++", "---"))
    out.append(Check("minimal edit: markdown cell kept, <= 12 changed lines",
                     "# MAGIC %md" in cur and "UNKNOWN" in cur.split("# COMMAND")[0] and 1 <= changed <= 12, 2, f"{changed} changed lines"))
    a = answer.lower()
    out.append(Check("answer names both root causes",
                     bool(re.search(r"ansi|cast|n/a|try_cast|not a number|invalid", a))
                     and bool(re.search(r"inner join|orphan|unknown|no matching|missing customer|left join", a)), 2))
    return out


def cleanup(ctx: Ctx) -> None:
    for j in find_jobs(job_name(ctx)):
        try:
            api("POST", "/api/2.1/jobs/delete", {"job_id": j["job_id"]})
        except RuntimeError:
            pass


MISSION = Mission(
    id="X2", title="HELD-OUT: diagnose and fix a failing job (1 loud + 1 silent bug)", capability="C7", difficulty=4,
    prompt=prompt, setup=setup, grade=grade, reference=reference, cleanup=cleanup, max_minutes=12,
)
