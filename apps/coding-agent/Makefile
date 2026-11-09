# OpenGenie coding agent — the deployment surface.
#
#   make            what can I do? (this is the default, on purpose)
#   make doctor     is this machine able to deploy at all?
#   make dev        run it locally, fake agent, for UI work
#   make dev-real   run it locally against the REAL agent and a real model
#   make check      the whole gate: types + unit tests (no network, no cloud)
#   make deploy     sync -> deploy -> VERIFY THE LIVE URL
#   make verify     is the deployment serving the code in this checkout?
#   make logs       the app's own logs
#
# Why this file exists. On 2026-11-09 the app reported "App started successfully" three times in a row
# while serving none of the work that had been written: no attach menu, no blob route, no vision field.
# Each cause was invisible to the deploy command itself, and each is now a step in `deploy`:
#
#   1. the app deploys from a WORKSPACE FOLDER, not from git, so `git push` changed nothing      -> sync
#   2. the front-end build skipped itself when dist/ already existed, so a cached bundle shipped -> prepare-app.sh always builds
#   3. SUCCEEDED means "the process started", NOT "it is running your code"                      -> verify probes the live URL
#
# So `deploy` is sync + deploy + verify, and `verify` fails loudly when the live app lacks what this
# checkout has. A deployment nobody probed is a guess.
#
# Every target is phony: this is a task runner, not a file builder. Declaring targets as files is how a
# Makefile starts claiming "up to date" about something that never ran.

SHELL := /bin/bash
.DEFAULT_GOAL := help
.PHONY: help doctor setup dev dev-real shell-pg check types unit audits vision \
        sync deploy-only deploy verify status url logs stop start clean clean-all

APP        := coding-agent
APP_DIR    := $(patsubst %/,%,$(dir $(abspath $(lastword $(MAKEFILE_LIST)))))
REPO       := $(abspath $(APP_DIR)/../..)
WS_SRC     := /Workspace/Users/raphael.mansuy@gmail.com/$(APP)
PY         := $(APP_DIR)/.venv/bin/python
WEB        := $(APP_DIR)/web
PORT       ?= 8062
REAL_PORT  ?= 8071
export DATABRICKS_HOST ?= https://dbc-1e111e44-3334.cloud.databricks.com

# Help is generated from the `##` comments, so it cannot fall out of step with the targets.
help: ## Show this help
	@printf '\n\033[1mOpenGenie coding agent\033[0m — deployment and development\n\n'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@printf '\n\033[2m  deploy = sync + deploy + verify. SUCCEEDED alone does not mean your code is live.\033[0m\n\n'

# ---------------------------------------------------------------- is this machine ready
doctor: ## Check the toolchain, the credentials, and the source the app will build
	@printf '\033[1m1. tools\033[0m\n'
	@for t in databricks python3 node npm git make; do \
	  if command -v $$t >/dev/null; then printf '  ok      %-11s %s\n' "$$t" "$$(command -v $$t)"; \
	  else printf '  \033[31mMISSING\033[0m %s\n' "$$t"; fi; done
	@printf '\033[1m2. the app itself\033[0m\n'
	@test -x $(PY) && printf '  ok      venv\n' || printf '  \033[31mMISSING\033[0m .venv — run: make setup\n'
	@test -d $(WEB)/node_modules && printf '  ok      web deps\n' || printf '  \033[33mabsent\033[0m web/node_modules — run: make setup\n'
	@printf '\033[1m3. credentials\033[0m\n'
	@databricks current-user me -o json 2>/dev/null | $(PY) -c 'import json,sys;print("  ok      signed in as", json.load(sys.stdin).get("userName"))' \
	  || printf '  \033[31mFAIL\033[0m    cannot authenticate — databricks auth login --host $(DATABRICKS_HOST)\n'
	@printf '\033[1m4. what is deployed\033[0m\n'
	@databricks apps get $(APP) -o json 2>/dev/null | $(PY) -c 'import json,sys;\
d=json.load(sys.stdin); dp=d.get("active_deployment") or {}; st=dp.get("status") or {};\
print("  ok      %s | %s | %s" % (d["name"], (d.get("compute_status") or {}).get("state"), st.get("state")))' \
	  || printf '  \033[33mabsent\033[0m  the app is not created — run: make deploy\n'
	@printf '\033[1m5. is the synced source current?\033[0m\n'
	@stale=0; \
	for probe in api/domain/blob.py api/adapters/acp/blocks.py web/scripts/vision-e2e.mjs; do \
	  if databricks workspace list "$(WS_SRC)/$$(dirname $$probe)" 2>/dev/null | grep -q "$$(basename $$probe)"; then \
	    printf '  ok      %s\n' "$$probe"; \
	  else printf '  \033[33mstale\033[0m   %s — the next deploy would ship old code\n' "$$probe"; stale=1; fi; \
	done; \
	if [ $$stale = 0 ]; then printf '\n  Ready. `make deploy` will sync, deploy and verify.\n'; fi

# ---------------------------------------------------------------- local development
setup: ## Install what is needed to run and test locally
	@test -d $(APP_DIR)/.venv || python3 -m venv $(APP_DIR)/.venv
	@$(APP_DIR)/.venv/bin/pip install -q -U pip
	@$(APP_DIR)/.venv/bin/pip install -q -r $(APP_DIR)/requirements.txt
	@$(APP_DIR)/.venv/bin/pip install -q pytest pytest-asyncio pytest-xdist 2>/dev/null || true
	@npm --prefix $(WEB) install --no-audit --no-fund
	@printf '  ready. Next: make dev\n'

dev: ## Run locally with the FAKE agent (deterministic, no model calls) on PORT=$(PORT)
	@printf '  http://127.0.0.1:$(PORT)   fake agent — scripted scenarios\n'
	@cd $(APP_DIR) && ./scripts/dev-token.sh $(PORT)

dev-real: ## Run locally against the REAL agent and a real model on REAL_PORT=$(REAL_PORT)
	@printf '  http://127.0.0.1:$(REAL_PORT)   real opencode + a serving endpoint — vision works here\n'
	@cd $(APP_DIR) && \
	  DATABRICKS_HOST=$(DATABRICKS_HOST) \
	  APP_AGENT_MODE=stdio \
	  APP_AGENT_CWD=$$(mktemp -d /tmp/agent-real-XXXXXX) \
	  APP_BLOB_DIR=$$(mktemp -d /tmp/blobs-real-XXXXXX) \
	  APP_DEV_TOKEN=$$(databricks auth token --host $(DATABRICKS_HOST) -o json | $(PY) -c 'import json,sys;print(json.load(sys.stdin)["access_token"])') \
	  $(PY) -m uvicorn api.main:app --host 127.0.0.1 --port $(REAL_PORT) --log-level warning

shell-pg: ## A throwaway Postgres for the migration tests
	@cd $(APP_DIR) && ./scripts/pg-test.sh start

# ---------------------------------------------------------------- the gate
check: types unit ## Everything that must pass before a deploy (no cloud, no network)
	@printf '\n\033[1mcheck: all green\033[0m\n'

types: ## TypeScript, and no Python that fails to import
	@printf '\033[1mtsc\033[0m\n'
	@cd $(WEB) && npx tsc -b --noEmit && printf '  ok      no type errors\n'

unit: ## pytest + vitest
	@printf '\033[1mpytest\033[0m\n'
	@cd $(APP_DIR) && $(PY) -m pytest tests -q 2>&1 | tail -2
	@printf '\033[1mvitest\033[0m\n'
	@cd $(WEB) && npx vitest run 2>&1 | grep -E 'Test Files|Tests '

audits: ## Accessibility, overflow and layout shift, against a running app on PORT
	@printf '\033[1maudits against http://127.0.0.1:$(PORT)\033[0m\n'
	@cd $(WEB) && \
	  APP_URL=http://127.0.0.1:$(PORT) node scripts/a11y-audit.mjs 2>&1 | grep TOTAL; \
	  for w in 1480 1180 900; do APP_URL=http://127.0.0.1:$(PORT) WIDTHS=$$w node scripts/overflow-audit.mjs 2>&1 | grep TOTAL; done; \
	  APP_URL=http://127.0.0.1:$(PORT) node scripts/cls-audit.mjs 2>&1 | tail -1

vision: ## Prove the model can READ an image (needs dev-real on REAL_PORT)
	@cd $(WEB) && APP_URL=http://127.0.0.1:$(REAL_PORT) node scripts/vision-e2e.mjs

# ---------------------------------------------------------------- deployment
sync: ## Copy the TRACKED files into the workspace folder the app deploys from
	@printf '\033[1msync\033[0m    git ls-files -> $(WS_SRC)\n'
	@cd $(APP_DIR) && ./scripts/sync-app-source.sh "$(WS_SRC)"

deploy-only: ## Deploy and wait for a terminal state (does not verify)
	@printf '\033[1mdeploy\033[0m  $(APP)\n'
	@cd $(APP_DIR) && databricks apps deploy $(APP) --wait 2>&1 | tail -5

deploy: sync deploy-only verify ## sync -> deploy -> verify the LIVE url. The only target that fully deploys

verify: ## Is the LIVE app serving THIS checkout? Fails when it is not.
	@cd $(APP_DIR) && ./scripts/verify-deployed.sh

status: ## What is deployed right now
	@databricks apps get $(APP) -o json 2>/dev/null | $(PY) -c 'import json,sys;\
d=json.load(sys.stdin); dp=d.get("active_deployment") or {}; st=dp.get("status") or {};\
print("  app        ", d["name"]);\
print("  compute    ", (d.get("compute_status") or {}).get("state"));\
print("  deployment ", dp.get("deployment_id"));\
print("  created    ", dp.get("create_time"));\
print("  status     ", st.get("state"), "-", (st.get("message") or "")[:60]);\
print("  url        ", d.get("url"))'

url: ## Print the deployed URL
	@databricks apps get $(APP) -o json 2>/dev/null | $(PY) -c 'import json,sys;print(json.load(sys.stdin).get("url",""))'

logs: ## The app's own logs
	@databricks apps logs $(APP) --tail-lines 120 2>&1 | tail -120

stop: ## Stop the deployed app
	@databricks apps stop $(APP) >/dev/null && printf '  stopped $(APP)\n'

start: ## Start the deployed app
	@databricks apps start $(APP) >/dev/null && printf '  started $(APP)\n'

clean: ## Remove local build output
	@rm -rf $(WEB)/dist && printf '  removed web/dist\n'

clean-all: clean ## ...and node_modules and caches
	@rm -rf $(WEB)/node_modules $(APP_DIR)/.pytest_cache $(APP_DIR)/.ruff_cache
	@printf '  removed node_modules and caches\n'
