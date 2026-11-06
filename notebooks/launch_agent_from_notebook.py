# Databricks notebook source
# MAGIC %md
# MAGIC # Run a coding agent from a Databricks notebook (no local shell needed)
# MAGIC
# MAGIC This notebook asks Databricks for a small temporary Linux machine (a "sandbox"), installs a coding agent
# MAGIC in it, and lets you give the agent tasks. Run the cells from top to bottom.
# MAGIC
# MAGIC * Needs **serverless compute** (standard library only) and access to the AI Gateway `system.ai.sandbox` service.
# MAGIC * The agent can only **write** to the one schema and one folder you name in step 5b.
# MAGIC * Full walkthrough: `docs/tutorial.md`.

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 1 · Helpers (just run this cell)

# COMMAND ----------
import base64, getpass, io, json, os, tarfile, time, urllib.request

HOST = "https://" + spark.conf.get("spark.databricks.workspaceUrl")
SESSION_TOKEN = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
EP = f"{HOST}/ai-gateway/mcp-services/system.ai.sandbox"


def rpc(method, params):
    req = urllib.request.Request(
        EP, method="POST",
        data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(),
        headers={"Authorization": f"Bearer {SESSION_TOKEN}", "Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream"})
    raw = urllib.request.urlopen(req, timeout=300).read().decode()
    for line in raw.splitlines():
        if line.startswith("data: "):
            raw = line[6:]
    return json.loads(raw)["result"]


def tool(name, **args):
    r = rpc("tools/call", {"name": name, "arguments": args})
    return "\n".join(c.get("text", "") for c in r.get("content", []))


def sh(sandbox_id, script, timeout=170):
    """Run a shell script in the sandbox. One call is cut after about 180 seconds."""
    b = base64.b64encode(script.encode()).decode()
    return tool("run_code", sandbox_id=sandbox_id, language="sh", timeout_seconds=timeout,
                code=f"echo '{b}' | base64 -d > /tmp/_s.sh; bash /tmp/_s.sh")


def put_tree(sandbox_id, local_dir, remote_dir, include=("templates", "mcp")):
    """Copy the kit folders from a Git folder under /Workspace into the sandbox (secrets and caches are never copied)."""
    skip = {".env", ".git", "__pycache__", ".venv", "results"}
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name in include:
            tar.add(os.path.join(local_dir, name), arcname=name,
                    filter=lambda ti: None if skip & set(ti.name.split("/")) else ti)
    data = base64.b64encode(buf.getvalue()).decode()
    parts = [data[i:i + 60000] for i in range(0, len(data), 60000)]
    for i, part in enumerate(parts):
        tool("run_code", sandbox_id=sandbox_id, language="sh", code=f"echo -n '{part}' {'>' if i == 0 else '>>'} /tmp/_up.b64")
    return sh(sandbox_id, f"mkdir -p {remote_dir} && base64 -d /tmp/_up.b64 | tar xz -C {remote_dir} && ls {remote_dir}")


def ask(sandbox_id, request, max_minutes=20):
    """Give the agent a task and wait for its report (works for tasks longer than one 180-second call)."""
    q = base64.b64encode(request.encode()).decode()
    sh(sandbox_id, f"""export DATABRICKS_HOST={HOST}
cd ~/agent-work && rm -f run.done run.log
echo '{q}' | base64 -d > q.txt
nohup bash -c 'bash ask.sh "$(cat q.txt)" > run.log 2>&1; touch run.done' >/dev/null 2>&1 &
echo started""")
    waited = 0
    while waited < max_minutes * 60:
        time.sleep(15)
        waited += 15
        if "yes" in sh(sandbox_id, "[ -f ~/agent-work/run.done ] && echo yes || echo no"):
            break
    return sh(sandbox_id, "tail -n 60 ~/agent-work/run.log")

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 2 · Get a sandbox (your temporary Linux machine)

# COMMAND ----------
sandbox_id = json.loads(tool("create_sandbox"))["sandbox_id"]
print("sandbox:", sandbox_id)
print(sh(sandbox_id, "uname -sm; databricks --version; node --version"))

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 3 · Put the agent kit in the sandbox
# MAGIC Option A copies it from GitHub. Option B copies it from a Git folder in your workspace
# MAGIC (change the path). Use one of them.

# COMMAND ----------
KIT_REPO = "https://github.com/raphaelmansuy/edgegenie"
print(sh(sandbox_id, f"rm -rf ~/edgegenie && git clone --depth 1 {KIT_REPO} ~/edgegenie 2>&1 | tail -1; ls ~/edgegenie/templates"))   # Option A

# print(put_tree(sandbox_id, "/Workspace/Users/YOU@example.com/edgegenie", "~/edgegenie"))                                          # Option B

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 4 · Give the agent your token
# MAGIC Create a personal access token under **Settings, Developer, Access tokens** (a short lifetime is best).
# MAGIC Paste it in the box that appears. It is saved only inside the sandbox, readable only by you, and never printed.

# COMMAND ----------
agent_token = getpass.getpass("Paste your Databricks token: ")
b = base64.b64encode(agent_token.encode()).decode()
sh(sandbox_id, f"umask 077; echo '{b}' | base64 -d > /tmp/dbx_token.txt")
del agent_token, b
print(sh(sandbox_id, f"export DATABRICKS_HOST={HOST}; unset DATABRICKS_CONFIG_FILE DATABRICKS_CONFIG_PROFILE; "
                     "DATABRICKS_TOKEN=$(cat /tmp/dbx_token.txt) databricks current-user me -o json | python3 -c \"import json,sys;print('signed in as', json.load(sys.stdin)['userName'])\""))

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 5 · Install the agent

# COMMAND ----------
print(sh(sandbox_id, f"export DATABRICKS_HOST={HOST}; cd ~/edgegenie && bash templates/setup_agent.sh"))

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 5b · Start the tool server and choose the only place the agent may write
# MAGIC Change the two names below to a schema and a folder you do not mind the agent filling with test objects.

# COMMAND ----------
SCRATCH_SCHEMA = "workspace.agent_scratch"                          # the only schema the agent may write to
SCRATCH_FOLDER = "/Workspace/Users/YOU@example.com/agent_scratch"   # the only folder the agent may write to
print(sh(sandbox_id, f"export DATABRICKS_HOST={HOST}; cd ~/agent-work && bash start_mcp.sh {SCRATCH_SCHEMA} {SCRATCH_FOLDER}"))

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 6 · Ask the agent to do something
# MAGIC A read-only question first.

# COMMAND ----------
print(ask(sandbox_id, "Which three pickup zip codes in samples.nyctaxi.trips have the highest total fare_amount? Show the SQL you ran and the numbers."))

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 7 · Ask for something real: build a notebook, run it, prove it works
# MAGIC The agent writes into your scratch folder, runs the notebook, and reports what happened.

# COMMAND ----------
print(ask(sandbox_id, f"""Create a Databricks notebook at {SCRATCH_FOLDER}/taxi_hours with a title, then cells that read samples.nyctaxi.trips and
(1) count trips and total fare by pickup hour, (2) chart total fare by hour, (3) end with dbutils.notebook.exit(<number of hours covered>).
Run the notebook. Fix any error. Tell me the exit value you got."""))

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 8 · See the safety fence work
# MAGIC Ask for something outside the allowed schema. The tool server (not the agent) should refuse.

# COMMAND ----------
print(ask(sandbox_id, "Create a table workspace.default.not_allowed_demo with one row, then tell me exactly what happened."))

# COMMAND ----------
# MAGIC %md
# MAGIC ## Step 9 · Tidy up
# MAGIC Stop the tool server. The sandbox and everything on its disk disappear on their own;
# MAGIC what the agent created in your workspace stays until you delete it.

# COMMAND ----------
print(sh(sandbox_id, "cd ~/agent-work && bash start_mcp.sh stop"))
print(tool("delete_sandbox", sandbox_id=sandbox_id))
dbutils.notebook.exit("done")
