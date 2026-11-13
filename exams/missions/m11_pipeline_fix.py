"""AG-55: repair a pipeline source in place and observe a successful native update."""

from lib import (
    Check,
    Mission,
    api,
    export_nb,
    import_nb,
    mkdirs,
    sql,
    sql_val,
    table_exists,
)
from lifecycle import wait_for, replace_fixture

BAD = '# Databricks notebook source\nimport dlt\n@dlt.table(name="ag014_numbers")\ndef numbers():\n    return spark.range(3).selectExpr("BROKEN AS id")\n'
FIXED = BAD.replace("BROKEN AS id", "id AS id")


def setup(ctx):
    sql("CREATE SCHEMA IF NOT EXISTS " + ctx.schema)
    mkdirs(ctx.home)
    import_nb(ctx.home + "/pipeline_source", BAD)
    name = ctx.extra.get("jobPrefix", ctx.run_id + "_") + "pipeline"
    pid = api(
        "POST",
        "/api/2.0/pipelines",
        {
            "name": name,
            "catalog": ctx.schema.split(".")[0],
            "target": ctx.schema.split(".")[1],
            "serverless": True,
            "continuous": False,
            "libraries": [{"notebook": {"path": ctx.home + "/pipeline_source"}}],
        },
    )["pipeline_id"]
    ctx.extra["pipelineId"] = pid


def prompt(ctx):
    return f"""Fix the unresolved BROKEN expression in pipeline {ctx.extra["pipelineId"]}, source notebook {ctx.home}/pipeline_source, using a minimal revision-bound edit.
Keep the original pipeline, run a normal update as me, observe it completing, and verify {ctx.schema}.ag014_numbers has exactly IDs 0, 1, 2. Do not use a full refresh."""


def reference(ctx):
    replace_fixture(ctx.home + "/pipeline_source", BAD, FIXED)
    pid = ctx.extra["pipelineId"]
    uid = api("POST", f"/api/2.0/pipelines/{pid}/updates", {"full_refresh": False})[
        "update_id"
    ]
    result = wait_for(
        lambda: api("GET", f"/api/2.0/pipelines/{pid}/updates/{uid}")["update"],
        lambda r: r["state"] in ("COMPLETED", "FAILED", "CANCELED"),
    )
    return f"pipeline_id={pid} update_id={uid} state={result['state']}"


def grade(ctx, answer):
    row = api("GET", "/api/2.0/pipelines/" + ctx.extra["pipelineId"])
    updates = api(
        "GET",
        "/api/2.0/pipelines/" + ctx.extra["pipelineId"] + "/updates",
        params={"max_results": 1},
    ).get("updates", [])
    full = ctx.schema + ".ag014_numbers"
    values = False
    if table_exists(full):
        # One row per generated ID; metadata is grounded before querying the fixture output.
        metadata = api("GET", "/api/2.1/unity-catalog/tables/" + full)
        if any(c["name"] == "id" for c in metadata.get("columns", [])):
            values = [
                [str(v) for v in row]
                for row in sql(f"SELECT id FROM {full} ORDER BY id")
            ] == [["0"], ["1"], ["2"]]
    return [
        Check(
            "original pipeline retains source",
            any(
                l.get("notebook", {}).get("path") == ctx.home + "/pipeline_source"
                for l in row["spec"].get("libraries", [])
            ),
            1,
        ),
        Check(
            "minimal source repair",
            export_nb(ctx.home + "/pipeline_source") == FIXED,
            3,
        ),
        Check(
            "latest native update completed",
            bool(updates) and updates[0]["state"] == "COMPLETED",
            3,
        ),
        Check("actual output IDs are 0, 1, 2", values, 3),
    ]


def cleanup(ctx):
    if ctx.extra.get("pipelineId"):
        api("DELETE", "/api/2.0/pipelines/" + ctx.extra["pipelineId"])


MISSION = Mission(
    "M11",
    "Repair a pipeline and observe its output",
    "AG-55",
    4,
    prompt,
    setup,
    grade,
    reference,
    cleanup,
    max_minutes=18,
)
