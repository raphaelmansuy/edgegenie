#!/bin/bash
# Probe which Databricks features this workspace supports, so exams only
# specify missions that can actually run here.
set -u
cd "$(dirname "$0")/.."
H=https://dbc-cb61f1e1-bd8e.cloud.databricks.com
T=$(grep TOKEN .env | cut -d= -f2)
probe() {
  local code
  code=$(curl -s -o /tmp/p.json -w "%{http_code}" -H "Authorization: Bearer $T" "$H$1")
  echo "[$code] $1  $(head -c 200 /tmp/p.json | tr '\n' ' ')"
}
echo "== Lakebase (database instances) =="; probe /api/2.0/database/instances
echo "== Apps ==";                          probe /api/2.0/apps
echo "== Pipelines ==";                     probe "/api/2.0/pipelines?max_results=2"
echo "== Jobs ==";                          probe "/api/2.1/jobs/list?limit=2"

echo "== Serverless notebook run via runs/submit (no cluster spec) =="
P=/Users/raphael.mansuy@gmail.com/_probe_nb
B=$(printf '# Databricks notebook source\nprint("probe-ok", 6*7)\n' | base64)
curl -s -o /dev/null -X POST -H "Authorization: Bearer $T" -H "Content-Type: application/json" \
  -d "{\"path\":\"$P\",\"format\":\"SOURCE\",\"language\":\"PYTHON\",\"content\":\"$B\",\"overwrite\":true}" \
  $H/api/2.0/workspace/import
curl -s -X POST -H "Authorization: Bearer $T" -H "Content-Type: application/json" \
  -d "{\"run_name\":\"probe\",\"tasks\":[{\"task_key\":\"t\",\"notebook_task\":{\"notebook_path\":\"$P\"}}]}" \
  $H/api/2.1/jobs/runs/submit | tee /tmp/sub.json
echo
