"""AG-55: save a parameterized native Query in the isolated mission folder, without compute."""

from lib import Check, Mission, api, mkdirs, warehouse
from lifecycle import queries, delete_owned_query, normalize

TEXT = "SELECT :amount + 1 AS incremented"


def setup(ctx):
    mkdirs(ctx.home)
    ctx.extra["queryWarehouse"] = warehouse()
    ctx.extra["queryName"] = "agent014-" + ctx.run_id + "-parameterized"


def matches(ctx):
    return [
        row
        for q in queries()
        if q.get("display_name") == ctx.extra["queryName"]
        for row in [api("GET", "/api/2.0/sql/queries/" + q["id"])]
        if row.get("lifecycle_state") != "TRASHED"
        and normalize(row.get("parent_path", "")) == normalize(ctx.home)
    ]


def prompt(ctx):
    return f"""Create one new native saved Query named exactly {ctx.extra["queryName"]} in workspace folder {ctx.home}, using warehouse {ctx.extra["queryWarehouse"]} and VIEWER run-as mode.
Its SQL text must be exactly: {TEXT}
Keep :amount as a named parameter. Read back the saved definition. Do not execute SQL, inline a parameter value, or create duplicate Queries."""


def reference(ctx):
    row = api(
        "POST",
        "/api/2.0/sql/queries",
        {
            "query": {
                "display_name": ctx.extra["queryName"],
                "parent_path": ctx.home,
                "query_text": TEXT,
                "warehouse_id": ctx.extra["queryWarehouse"],
                "run_as_mode": "VIEWER",
            }
        },
    )
    ctx.extra["createdQueryId"] = row["id"]
    current = api("GET", "/api/2.0/sql/queries/" + row["id"])
    return "query_id=" + current["id"]


def grade(ctx, answer):
    found = matches(ctx)
    row = (
        api("GET", "/api/2.0/sql/queries/" + found[0]["id"]) if len(found) == 1 else {}
    )
    return [
        Check("one native Query in the isolated parent", len(found) == 1, 3),
        Check(
            "named parameter SQL preserved exactly", row.get("query_text") == TEXT, 4
        ),
        Check(
            "requested warehouse retained",
            row.get("warehouse_id") == ctx.extra["queryWarehouse"],
            1,
        ),
        Check("native VIEWER run-as mode", row.get("run_as_mode") == "VIEWER", 2),
    ]


def cleanup(ctx):
    ids = {r["id"] for r in matches(ctx)}
    if ctx.extra.get("createdQueryId"):
        ids.add(ctx.extra["createdQueryId"])
    for query_id in ids:
        delete_owned_query(query_id, ctx.home)


MISSION = Mission(
    "M13",
    "Save a native parameterized Query",
    "AG-55",
    3,
    prompt,
    setup,
    grade,
    reference,
    cleanup,
    uses_schema=False,
)
