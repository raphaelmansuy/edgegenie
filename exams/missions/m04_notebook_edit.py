"""M4 - Edit an existing notebook: fix 1 loud + 2 silent bugs with a minimal diff (C6)."""
from __future__ import annotations

import difflib
import json

from lib import Check, Ctx, Mission, export_nb, import_nb, mkdirs, run_notebook, sql

SEED = '''# Databricks notebook source
# MAGIC %md
# MAGIC # Fare per mile report
# MAGIC Which pickup zip has the highest fare per mile, among zips with enough long trips?

# COMMAND ----------
import json
from pyspark.sql import functions as F

MIN_TRIPS = 100
df = spark.table("samples.nyctaxi.trips")

# COMMAND ----------
# Fare per mile per pickup zip, counting only trips LONGER than one mile
long_trips = df.filter(F.col("trip_distance") < 1)
agg = (long_trips.groupBy("pickup_zip")
       .agg((F.sum("fare") / F.sum("trip_distance")).alias("fare_per_mile"),
            F.count("*").alias("n")))

# COMMAND ----------
# Keep only zips with at least MIN_TRIPS long trips, then pick the HIGHEST fare per mile
eligible = agg.filter(F.col("n") >= MIN_TRIPS)
best = eligible.first()

# COMMAND ----------
dbutils.notebook.exit(json.dumps({"zip": best["pickup_zip"], "fare_per_mile": round(best["fare_per_mile"], 4)}))
'''

GOLD = """SELECT pickup_zip, round(sum(fare_amount)/sum(trip_distance), 4) AS fpm
FROM samples.nyctaxi.trips WHERE trip_distance > 1
GROUP BY pickup_zip HAVING count(*) >= 100 ORDER BY fpm DESC LIMIT 1"""

KEEP_LINES = ["MIN_TRIPS = 100", "# Fare per mile report",
              'dbutils.notebook.exit(json.dumps({"zip": best["pickup_zip"], "fare_per_mile": round(best["fare_per_mile"], 4)}))']


def nb_path(ctx: Ctx) -> str:
    return f"{ctx.home}/m4_fare_report"


def prompt(ctx: Ctx) -> str:
    return f"""The notebook {nb_path(ctx)} is supposed to find the pickup zip with the highest fare per mile among zips that have at least MIN_TRIPS trips longer than one mile, and return it with dbutils.notebook.exit. Its comments describe the intended behaviour. It currently does not produce a correct answer.

Fix it in place (same path). Constraints:
- Make the smallest change that fixes the problem: do not rewrite the notebook, keep the cell structure, comments, MIN_TRIPS and the final exit cell as they are.
- Run it on serverless compute after your fix and show me the exit value.
- Verify the exit value independently with a SQL query against samples.nyctaxi.trips and tell me whether the two agree.
- List every defect you found, including any that did not raise an error."""


def setup(ctx: Ctx) -> None:
    mkdirs(ctx.home)
    import_nb(nb_path(ctx), SEED)


def reference(ctx: Ctx) -> str:
    fixed = (SEED.replace('F.col("trip_distance") < 1', 'F.col("trip_distance") > 1')
             .replace('F.sum("fare")', 'F.sum("fare_amount")')
             .replace("best = eligible.first()", 'best = eligible.orderBy(F.desc("fare_per_mile")).first()'))
    import_nb(nb_path(ctx), fixed)
    r = run_notebook(nb_path(ctx))
    return (f"Defects: 1) column fare does not exist, should be fare_amount; 2) filter used < 1 instead of > 1; "
            f"3) first() without orderBy picks an arbitrary zip. Exit value {r['result']}. SQL check agrees.")


def grade(ctx: Ctx, answer: str) -> list[Check]:
    src = export_nb(nb_path(ctx))
    if src is None:
        return [Check("notebook still exists", False, 3)]
    out = [Check("notebook still exists", True, 1)]
    gz, gf = sql(GOLD)[0]
    r = run_notebook(nb_path(ctx))
    out.append(Check("runs successfully on serverless", r["ok"], 2, f"{r['state']} {str(r.get('error'))[:160]}"))
    ok = False
    detail = r.get("result") or "no result"
    if r["ok"] and r.get("result"):
        try:
            got = json.loads(r["result"])
            ok = str(got["zip"]) == str(gz) and abs(float(got["fare_per_mile"]) - float(gf)) < 0.001
            detail = f"got {got}; want zip={gz} fpm={gf}"
        except Exception as e:  # noqa: BLE001
            detail = str(e)
    out.append(Check("exit value equals the golden answer (all 3 defects fixed)", ok, 5, detail))
    kept = [k for k in KEEP_LINES if k in src]
    out.append(Check("protected lines preserved verbatim", len(kept) == len(KEEP_LINES), 1, f"{len(kept)}/{len(KEEP_LINES)}"))
    changed = [l for l in difflib.unified_diff(SEED.splitlines(), src.splitlines(), lineterm="", n=0)
               if l[:1] in "+-" and l[:3] not in ("+++", "---")]
    out.append(Check("minimal diff (<= 12 changed lines)", len(changed) <= 12, 2, f"{len(changed)} changed lines"))
    out.append(Check("cell structure preserved",
                     src.count("# COMMAND ----------") == SEED.count("# COMMAND ----------"), 1))
    out.append(Check("no hard-coded answer", str(gz) not in src, 1))
    a = (answer or "").lower()
    out.append(Check("lists all three defects (fare column, < 1 filter, unordered first)",
                     "fare_amount" in a and ("< 1" in a or "<1" in a or "inverted" in a or "wrong comparison" in a or "longer" in a)
                     and ("orderby" in a or "order by" in a or "sort" in a or "arbitrary" in a or "unordered" in a), 2))
    out.append(Check("reports an independent SQL verification", "sql" in a and ("agree" in a or "match" in a), 1))
    return out


MISSION = Mission(
    id="M4", title="Notebook editing: fix loud + silent bugs minimally", capability="C6", difficulty=4,
    prompt=prompt, setup=setup, grade=grade, reference=reference, max_minutes=12,
)
