"""M3 - Create a useful data-analysis notebook (C5: author a notebook that runs)."""
from __future__ import annotations

import json
import re

from lib import (Check, Ctx, Mission, delete_path, export_nb, import_nb, mkdirs,
                 run_notebook, sql, sql_val)

GOLD_SQL = {
    "n_trips": "SELECT count(*) FROM samples.nyctaxi.trips",
    "peak_hour": ("SELECT hour(tpep_pickup_datetime) FROM samples.nyctaxi.trips GROUP BY 1 "
                  "ORDER BY count(*) DESC, 1 ASC LIMIT 1"),
    "avg_fare_per_mile": ("SELECT round(sum(fare_amount)/sum(trip_distance), 2) FROM samples.nyctaxi.trips "
                          "WHERE trip_distance > 0"),
}


def nb_path(ctx: Ctx) -> str:
    return f"{ctx.home}/m3_taxi_analysis"


def prompt(ctx: Ctx) -> str:
    return f"""Create a Databricks notebook (SOURCE format, Python) at the workspace path {nb_path(ctx)} that a business analyst could open and read top to bottom to understand demand patterns in the NYC taxi sample table samples.nyctaxi.trips.

Required structure:
1. A first markdown cell with a title, the business question, and the data source.
2. Analysis cells, each preceded by a short markdown cell saying what it shows, covering at least: (a) trips by hour of day, (b) fare behaviour by trip-distance bucket, (c) the top 10 pickup zips by trip count.
3. At least two visualizations (display() charts or matplotlib).
4. A final markdown "Findings" cell with at least three concrete findings that quote numbers computed by the notebook.
5. The very last cell must call dbutils.notebook.exit() with a JSON string with exactly these keys: n_trips (total rows in the table), peak_hour (hour 0-23 with the most pickups, ties -> smaller hour), avg_fare_per_mile (sum(fare_amount)/sum(trip_distance) over trips with trip_distance > 0, rounded to 2 decimals). Compute them from the data in code; never hard-code them.

The notebook will be executed on serverless compute, so it must run end to end without errors. Run it yourself to prove that before you finish, and tell me the exit value."""


def setup(ctx: Ctx) -> None:
    mkdirs(ctx.home)


REFERENCE_NB = '''# Databricks notebook source
# MAGIC %md
# MAGIC # NYC taxi demand patterns
# MAGIC **Question:** when and where is demand highest, and how does fare scale with distance?
# MAGIC **Source:** `samples.nyctaxi.trips`

# COMMAND ----------
import json
from pyspark.sql import functions as F
df = spark.table("samples.nyctaxi.trips")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Trips by hour of day

# COMMAND ----------
by_hour = df.groupBy(F.hour("tpep_pickup_datetime").alias("hour")).count().orderBy("hour")
display(by_hour)

# COMMAND ----------
# MAGIC %md
# MAGIC ## Fare by distance bucket

# COMMAND ----------
b = df.withColumn("bucket", F.when(F.col("trip_distance") < 1, "<1mi").when(F.col("trip_distance") < 3, "1-3mi").otherwise("3mi+"))
display(b.groupBy("bucket").agg(F.avg("fare_amount").alias("avg_fare"), F.count("*").alias("trips")))

# COMMAND ----------
# MAGIC %md
# MAGIC ## Top 10 pickup zips
# MAGIC top zips

# COMMAND ----------
display(df.groupBy("pickup_zip").count().orderBy(F.desc("count")).limit(10))

# COMMAND ----------
# MAGIC %md
# MAGIC ## Findings
# MAGIC 1. Peak demand is in the evening. 2. Longer trips cost more. 3. Midtown zips dominate.

# COMMAND ----------
n = df.count()
peak = by_hour.orderBy(F.desc("count"), F.asc("hour")).first()["hour"]
fpm = df.filter("trip_distance > 0").agg((F.sum("fare_amount") / F.sum("trip_distance")).alias("x")).first()["x"]
dbutils.notebook.exit(json.dumps({"n_trips": n, "peak_hour": peak, "avg_fare_per_mile": round(fpm, 2)}))
'''


def reference(ctx: Ctx) -> str:
    import_nb(nb_path(ctx), REFERENCE_NB)
    r = run_notebook(nb_path(ctx))
    return f"I ran it; exit value: {r['result']}"


def grade(ctx: Ctx, answer: str) -> list[Check]:
    src = export_nb(nb_path(ctx))
    if src is None:
        return [Check("notebook exists at the requested path", False, 3, nb_path(ctx))]
    out = [Check("notebook exists at the requested path", True, 1)]
    cells = [c for c in re.split(r"\n# COMMAND ----------\n", src) if c.strip()]
    md = [c for c in cells if "# MAGIC %md" in c]
    first_md = cells[0].count("# MAGIC %md") > 0 if cells else False
    out.append(Check("is a Databricks SOURCE notebook with >= 8 cells",
                     src.startswith("# Databricks notebook source") and len(cells) >= 8, 1,
                     f"{len(cells)} cells"))
    out.append(Check("first cell is markdown (title/question/source)", first_md, 1))
    out.append(Check(">= 5 markdown cells (narrative, not just code)", len(md) >= 5, 1, f"{len(md)} md"))
    out.append(Check("reads samples.nyctaxi.trips", "samples.nyctaxi.trips" in src, 1))
    viz = len(re.findall(r"\bdisplay\(|plt\.|\.plot\(|px\.", src))
    out.append(Check(">= 2 visualizations", viz >= 2, 1, f"{viz} viz calls"))
    out.append(Check("covers hour, distance bucket, top-10 zips",
                     all(re.search(p, src, re.I) for p in (r"hour", r"bucket|distance", r"limit\(10\)|top\s*10|LIMIT 10")),
                     1))
    out.append(Check("ends with dbutils.notebook.exit", "dbutils.notebook.exit" in cells[-1] if cells else False, 1))
    gold = {k: sql_val(v) for k, v in GOLD_SQL.items()}
    hard = [k for k in ("n_trips",) if re.search(rf"\b{gold[k]}\b", src)]
    out.append(Check("does not hard-code the exit values", not hard, 1, f"hard-coded: {hard}"))
    r = run_notebook(nb_path(ctx))
    out.append(Check("executes end to end on serverless", r["ok"], 4, f"{r['state']} {str(r.get('error'))[:200]}"))
    ok_vals = False
    detail = r.get("result") or "no exit value"
    if r["ok"] and r.get("result"):
        try:
            got = json.loads(r["result"])
            ok_vals = (int(got["n_trips"]) == int(gold["n_trips"])
                       and int(got["peak_hour"]) == int(gold["peak_hour"])
                       and abs(float(got["avg_fare_per_mile"]) - float(gold["avg_fare_per_mile"])) < 0.011)
            detail = f"got {got} want {gold}"
        except Exception as e:  # noqa: BLE001
            detail = f"bad JSON: {e}"
    out.append(Check("exit JSON values equal the golden numbers", ok_vals, 4, detail))
    out.append(Check("agent reported an exit value / evidence of running",
                     bool(re.search(r"n_trips|peak_hour|SUCCESS|exit", answer or "", re.I)), 1))
    return out


MISSION = Mission(
    id="M3", title="Notebook authoring: demand-pattern analysis", capability="C5", difficulty=3,
    prompt=prompt, setup=setup, grade=grade, reference=reference, max_minutes=12,
)
