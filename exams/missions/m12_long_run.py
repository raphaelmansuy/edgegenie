"""AG-55: follow a long native run once, then save its unpredictable observed result."""

import json
from lib import Check, Mission, api, export_nb, import_nb, mkdirs
from lifecycle import wait_job

SOURCE = "# Databricks notebook source\nimport time, uuid\ntime.sleep(40)\ndbutils.notebook.exit(str(uuid.uuid4()))\n"


def setup(ctx):
    mkdirs(ctx.home)
    import_nb(ctx.home + "/long_run", SOURCE)
    name = ctx.extra.get("jobPrefix", ctx.run_id + "_") + "long_run"
    ctx.extra["longJob"] = api(
        "POST",
        "/api/2.1/jobs/create",
        {
            "name": name,
            "tasks": [
                {
                    "task_key": "long",
                    "notebook_task": {"notebook_path": ctx.home + "/long_run"},
                }
            ],
        },
    )["job_id"]


def prompt(ctx):
    return f"""Run job {ctx.extra["longJob"]} once as me. It intentionally takes longer than a tool wait; keep its operation handle and continue after the server observes success. Never resubmit it.
After success read the native notebook output. Create notebook {ctx.home}/observed_result whose source is exactly a Databricks notebook SOURCE header followed by one comment line containing the JSON object with keys run_id (the numeric top-level run ID) and result (the actual UUID exit value).
Do not change {ctx.home}/long_run. The result is generated at execution time; a predicted value does not count."""


def report_source(run_id, result):
    return (
        "# Databricks notebook source\n# "
        + json.dumps({"run_id": run_id, "result": result}, sort_keys=True)
        + "\n"
    )


def native_result(row):
    task = next(t for t in row["tasks"] if t["task_key"] == "long")
    return (
        api("GET", "/api/2.1/jobs/runs/get-output", params={"run_id": task["run_id"]})
        .get("notebook_output", {})
        .get("result")
    )


def reference(ctx):
    rid = api("POST", "/api/2.1/jobs/run-now", {"job_id": ctx.extra["longJob"]})[
        "run_id"
    ]
    row = wait_job(rid)
    if row["state"].get("result_state") != "SUCCESS":
        raise RuntimeError("Long fixture failed")
    result = native_result(row)
    import_nb(ctx.home + "/observed_result", report_source(rid, result))
    return f"run_id={rid} result={result}"


def grade(ctx, answer):
    runs = api(
        "GET",
        "/api/2.1/jobs/runs/list",
        params={"job_id": ctx.extra["longJob"], "limit": 2},
    ).get("runs", [])
    row = (
        api("GET", "/api/2.1/jobs/runs/get", params={"run_id": runs[0]["run_id"]})
        if runs
        else {}
    )
    success = row.get("state", {}).get("result_state") == "SUCCESS"
    result = native_result(row) if success else None
    source = export_nb(ctx.home + "/observed_result") or ""
    try:
        saved = json.loads(source.splitlines()[1].removeprefix("# "))
    except (ValueError, IndexError):
        saved = {}
    return [
        Check("exactly one top-level native run", len(runs) == 1, 2),
        Check(
            "native run succeeded after deliberate long wait",
            success and row.get("execution_duration", 0) >= 40000,
            3,
        ),
        Check(
            "saved report matches observed native output",
            bool(result) and saved == {"run_id": row.get("run_id"), "result": result},
            4,
        ),
        Check(
            "original long notebook unchanged",
            export_nb(ctx.home + "/long_run") == SOURCE,
            1,
        ),
    ]


def cleanup(ctx):
    if ctx.extra.get("longJob"):
        api("POST", "/api/2.1/jobs/delete", {"job_id": ctx.extra["longJob"]})


MISSION = Mission(
    "M12",
    "Continue after a long native run",
    "AG-55",
    4,
    prompt,
    setup,
    grade,
    reference,
    cleanup,
    max_minutes=15,
    uses_schema=False,
)
