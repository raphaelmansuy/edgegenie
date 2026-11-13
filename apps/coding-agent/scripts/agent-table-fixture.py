"""Owner-verified, isolated table E2E schema. Cleanup never force-deletes tables."""

import json, sys, os
from uuid import uuid4
from databricks.sdk import WorkspaceClient
from databricks.sdk.core import Config
from databricks.sdk.errors import NotFound

cfg = Config(profile=os.environ.get("EXAM_DATABRICKS_PROFILE", "opengenie-dev"))
assert cfg.host.rstrip("/") == "https://dbc-cb61f1e1-bd8e.cloud.databricks.com"
w = WorkspaceClient(config=cfg)
me = w.current_user.me()
assert me.user_name == "raphael.mansuy@gmail.com"
action = sys.argv[1]
if action == "create":
    tag = uuid4().hex[:10]
    name = "agent014_table_" + tag
    schema = w.schemas.create(name=name, catalog_name="workspace")
    print(
        json.dumps(
            {
                "schema": schema.full_name,
                "table": schema.full_name + ".created",
                "folder": "/Users/" + me.user_name + "/agent_scratch/agent014-table-" + tag,
            }
        )
    )
else:
    full = sys.argv[2]
    catalog, name = full.split(".")
    assert catalog == "workspace" and name.startswith("agent014_table_") and len(name) == 25
    schema = w.schemas.get(full)
    assert schema.owner == me.user_name
    if action == "inspect":
        try:
            table = w.tables.get(full + ".created")
            print(
                json.dumps(
                    {
                        "exists": True,
                        "owner": table.owner,
                        "tableId": table.table_id,
                        "columns": [{"name": c.name, "type": c.type_text} for c in table.columns],
                    }
                )
            )
        except NotFound:
            print(json.dumps({"exists": False}))
    elif action == "cleanup":
        assert not list(w.tables.list(catalog_name=catalog, schema_name=name)), (
            "Refusing to remove a nonempty E2E schema"
        )
        w.schemas.delete(full)
        print(json.dumps({"removedEmptySchema": full}))
    else:
        raise ValueError("Unknown action")
