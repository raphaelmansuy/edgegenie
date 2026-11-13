"""AG-55: repair failed tasks of the original run without rerunning its successful task."""

from lib import Check, Mission, api, export_nb, import_nb, mkdirs
from lifecycle import job_run, wait_job, wait_for, replace_fixture

GOOD = '# Databricks notebook source\ndbutils.notebook.exit("keep-successful-task")\n'
BAD = '# Databricks notebook source\nraise RuntimeError("AG014-repair-fixture")\n'
FIXED = '# Databricks notebook source\ndbutils.notebook.exit("repaired-task")\n'


def setup(ctx):
    mkdirs(ctx.home)
    import_nb(ctx.home + "/good", GOOD)
    import_nb(ctx.home + "/repair", BAD)
    name = ctx.extra.get("jobPrefix", ctx.run_id + "_") + "repair"
    jid = api(
        "POST",
        "/api/2.1/jobs/create",
        {
            "name": name,
            "tasks": [
                {
                    "task_key": "good",
                    "notebook_task": {"notebook_path": ctx.home + "/good"},
                },
                {
                    "task_key": "repair",
                    "depends_on": [{"task_key": "good"}],
                    "notebook_task": {"notebook_path": ctx.home + "/repair"},
                },
            ],
        },
    )["job_id"]
    ctx.extra["repairJob"] = jid
    rid = api("POST", "/api/2.1/jobs/run-now", {"job_id": jid})["run_id"]
    ctx.extra["repairRun"] = rid
    row = wait_job(rid)
    if row["state"].get("result_state") != "FAILED":
        raise RuntimeError("The repair fixture must begin with a failed run")
    ctx.extra["goodTaskRun"] = next(
        t["run_id"] for t in row["tasks"] if t["task_key"] == "good"
    )


def prompt(ctx):
    return f"""Fix notebook {ctx.home}/repair by replacing the fixture exception with dbutils.notebook.exit("repaired-task").
Repair only the failed tasks of original run {ctx.extra["repairRun"]} of job {ctx.extra["repairJob"]}; do not start a new run, replace the job, or rerun task good.
Observe the repaired run succeeding and report its run ID and repair ID. Keep notebook {ctx.home}/good byte-identical."""


def reference(ctx):
    replace_fixture(ctx.home + "/repair", BAD, FIXED)
    row = job_run(ctx.extra["repairRun"])
    body = {"run_id": ctx.extra["repairRun"], "rerun_all_failed_tasks": True}
    history = [
        r["id"]
        for r in row.get("repair_history", [])
        if r.get("type") == "REPAIR" and r.get("id") is not None
    ]
    if history:
        body["latest_repair_id"] = history[-1]
    repaired = api("POST", "/api/2.1/jobs/runs/repair", body)
    repair_id = repaired["repair_id"]

    def settled(row):
        repair = next(
            (
                r
                for r in row.get("repair_history", [])
                if r.get("id") == repair_id and r.get("type") == "REPAIR"
            ),
            None,
        )
        return bool(
            repair
            and repair.get("end_time")
            and repair.get("state", {}).get("life_cycle_state")
            in ("TERMINATED", "SKIPPED", "INTERNAL_ERROR")
        )

    wait_for(lambda: job_run(ctx.extra["repairRun"]), settled)
    return f"run_id={ctx.extra['repairRun']} repair_id={repaired['repair_id']}"


def grade(ctx, answer):
    row = job_run(ctx.extra["repairRun"])
    tasks = {t["task_key"]: t for t in row.get("tasks", [])}
    runs = api(
        "GET",
        "/api/2.1/jobs/runs/list",
        params={"job_id": ctx.extra["repairJob"], "limit": 2},
    ).get("runs", [])
    return [
        Check(
            "original run succeeded after a native repair",
            row["state"].get("result_state") == "SUCCESS"
            and bool(row.get("repair_history")),
            4,
        ),
        Check(
            "no replacement top-level run",
            len(runs) == 1 and runs[0]["run_id"] == ctx.extra["repairRun"],
            2,
        ),
        Check(
            "successful task kept its native run",
            tasks.get("good", {}).get("run_id") == ctx.extra["goodTaskRun"],
            2,
        ),
        Check(
            "successful notebook byte-identical",
            export_nb(ctx.home + "/good") == GOOD,
            1,
        ),
        Check(
            "failed notebook fixed exactly", export_nb(ctx.home + "/repair") == FIXED, 1
        ),
    ]


def cleanup(ctx):
    if ctx.extra.get("repairJob"):
        api("POST", "/api/2.1/jobs/delete", {"job_id": ctx.extra["repairJob"]})


MISSION = Mission(
    "M10",
    "Repair only failed job tasks",
    "AG-55",
    4,
    prompt,
    setup,
    grade,
    reference,
    cleanup,
    uses_schema=False,
    max_minutes=15,
)
