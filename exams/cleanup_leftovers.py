#!/usr/bin/env python3
"""Remove anything an interrupted exam run may have left behind (exam_* schemas,
<run>_* jobs, <run>-* Lakebase instances and projects, /exams workspace folders)."""
import re, sys
from lib import api, sql, delete_path, USER, CATALOG

for (name,) in sql(f"SELECT schema_name FROM {CATALOG}.information_schema.schemata WHERE schema_name LIKE 'exam\\_%'"):
    print("drop schema", name); sql(f"DROP SCHEMA IF EXISTS {CATALOG}.{name} CASCADE")
for j in api("GET", "/api/2.1/jobs/list", params={"limit": 100}).get("jobs", []):
    if re.match(r"^[xv][0-9a-f]{5}_", j["settings"].get("name", "")):
        print("delete job", j["settings"]["name"]); api("POST", "/api/2.1/jobs/delete", {"job_id": j["job_id"]})
for i in api("GET", "/api/2.0/database/instances").get("database_instances", []):
    if re.match(r"^[xv][0-9a-f]{5}-", i["name"]):
        print("delete instance", i["name"]); api("DELETE", f"/api/2.0/database/instances/{i['name']}", params={"purge": "true"})
# Lakebase Autoscaling projects (created through the newer `databricks postgres` API)
try:
    for pr in api("GET", "/api/2.0/postgres/projects").get("projects", []):
        pid = pr["name"].split("/")[-1]
        if re.match(r"^[xv][0-9a-f]{5}-", pid):
            print("delete postgres project", pid); api("DELETE", f"/api/2.0/postgres/projects/{pid}")
except RuntimeError as e:
    print("postgres projects: skipped:", str(e)[:120])
delete_path(f"/Users/{USER}/exams"); print("deleted /exams workspace folder")
