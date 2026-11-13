"""Configuration: one validated place. Fails fast at boot rather than weakening the fence later."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", extra="ignore")

    # identity: in Databricks the proxy supplies these; locally a dev user is used
    dev_user: str = "dev@example.com"
    require_forwarded_user: bool = False

    # agent
    agent_mode: Literal["fake", "stdio", "http"] = "fake"
    agent_command: str = "opencode acp"
    agent_cwd: str = "/tmp/agent-work"
    agent_config_dir: str = ""  # empty -> the default HOME
    agent_run_identity: str = ""  # S13: declarations fail closed until isolation is qualified

    # tools
    tool_mode: Literal["none", "subprocess"] = "none"
    tool_server_python: str = "python3"

    # Spec 014 phases remain opt-in until live release qualification.
    changes: bool = False
    operations: bool = False
    assets: bool = False
    evidence_v2: bool = False
    journal_v2: bool = False
    agent_workspace_demo: bool = False
    agent_ascode_demo: bool = False
    asset_kinds: list[str] = Field(default_factory=lambda:["job","pipeline","app","instance","job_run","pipeline_update","job_task_run","lineage","column_lineage","compute_usage","query_history"])
    agent_db_path: str = ""
    agent_key: str = ""
    agent_token_ceiling: int = Field(default=1000000, ge=1000)
    agent_money_ceiling: float = Field(default=10, gt=0, allow_inf_nan=False)
    agent_max_pass_cost: float = Field(default=0, ge=0, allow_inf_nan=False)
    agent_poll_seconds: float = Field(default=2, ge=.05, le=30)
    agent_native_concurrency: int = Field(default=8, ge=1, le=64)

    # models
    # The catalogue is data now: `seed/llm_models.yaml` plus discovery plus the registry. These two
    # fields remain for demo mode, where the fake agent advertises its own two models, and as an
    # additional allow-list in tests. They are NOT the deployed app's catalogue any more (spec 005 P7).
    #
    # Chosen by running the same tasks on every served model (specs 001/18): the non-reasoning
    # models call tools reliably; gpt-oss-120b often ended a turn after reasoning with no tool call.
    default_model: str = "databricks/databricks-llama-4-maverick"
    allowed_models: list[str] = Field(
        default_factory=lambda: [
            "databricks/databricks-llama-4-maverick",
            "databricks/system.ai.gpt-oss-120b",
            "databricks/system.ai.qwen3-next-80b-a3b-instruct",
            "databricks/databricks-meta-llama-3-3-70b-instruct",
            "databricks/databricks-claude-sonnet-4-5",
        ]
    )

    # -- the LLM registry (spec 005, 12 §Configuration) -------------------------------------
    #: Lakebase Postgres DSN. Unset -> the seed catalogue (C-5); unreachable -> degraded (E-15).
    llm_database_url: str = ""
    #: Lakebase (managed Postgres) by endpoint. Preferred over a DSN because the password is a
    #: short-lived OAuth token: a static DSN stops working within the hour. Format:
    #: `projects/{p}/branches/{b}/endpoints/{e}`. The host is read from the endpoint itself.
    llm_pg_endpoint: str = ""
    llm_pg_database: str = "databricks_postgres"
    #: Postgres role. Empty -> the app's own service principal (DATABRICKS_CLIENT_ID).
    llm_pg_user: str = ""
    #: Who may change the model catalogue and providers for everyone (comma-separated emails).
    #: Empty means nobody: a catalogue anyone can rewrite is a finding, not a default.
    llm_admins: str = ""
    #: Where the seed rows live. Empty -> the packaged `seed/llm_models.yaml`.
    llm_seed_path: str = ""
    #: base64 AES-256 KEK. Development and pilot only; its use is logged at boot.
    llm_kek: str = ""
    #: A Databricks secret scope holding the KEK, when one is attachable.
    llm_kek_scope: str = ""
    llm_kek_key: str = "llm-kek"
    #: Off by default: external calls move prompts and spend outside Unity Catalog (D12).
    llm_allow_external: bool = False
    llm_discovery_seconds: int = 300
    llm_probe_seconds: int = 900
    #: Vertex location. `global` is what the repository's working script uses.
    llm_vertex_location: str = "global"
    llm_vertex_project: str = ""
    #: Overrides for a proxy or a regional endpoint. Configuration, never a secret.
    llm_vertex_base_url: str = ""
    llm_openai_base_url: str = ""
    llm_anthropic_base_url: str = ""
    #: `dev` / `production`. A production app refuses a development KEK (R-5).
    app_env: str = "dev"

    #: Cross-origin origins, comma-separated. **Empty means no cross-origin grant at all**, which is
    #: correct for a deployment: uvicorn serves the built front end, so the browser is same-origin.
    #: Only a separate dev server needs this (`http://localhost:5173`). It is not a wildcard by
    #: default, because a wildcard on an app authenticated by a proxy lets any page a user visits
    #: call this API.
    cors_origins: str = ""

    #: How often the attachment sweeper runs. The *rules* are in `domain/retention.py` (one hour for a
    #: blob that never finished uploading, a day for one that was uploaded and never sent, never for
    #: one a turn references); this is only how often the rule is applied. 0 disables it, which is
    #: what a store that expires on its own wants.
    blob_sweep_seconds: int = Field(default=60, ge=0, le=86400)
    #: Demo mode only: add the seed catalogue to `allowed_models`, so the picker's groups, states and
    #: limit evidence can be exercised (and screenshotted) without a workspace. The e2e suite sets it.
    llm_demo_seed: bool = False

    # limits (see specs/001 12 and 15)
    max_concurrent_agents: int = Field(default=4, ge=1, le=64)
    max_tools: int = 24
    max_turns_per_session: int = 200
    stream_heartbeat_seconds: int = 10

    # Empty path is explicitly volatile (tests/demo); production requires a persistent journal.
    session_db_path: str = ""
    session_database_url: str = ""
    session_use_lakebase: bool = False
    # SQL is opt-in for live execution/creation until workspace interoperability is qualified.
    sql_run: bool = False
    sql_create: bool = False
    sql_db_path: str = ""
    sql_key: str = ""
    session_max_run_seconds: int = Field(default=21600, ge=1, le=604800)
    demo_event_delay: float = Field(default=0, ge=0, le=5)

    demo_scenario: str = "notebook"

    #: Run Python cells on serverless compute as the APP's service principal, for administrators only
    #: (APP_LLM_ADMINS). Off switch for an owner who does not want user code to run under the app's
    #: identity at all. SQL cells are unaffected: they run as the signed-in user.
    python_run: bool = True
    #: A persistent Python session (one serverless job that stays up, so variables survive between cells)
    #: or only one-shot runs. "auto" tries a session and falls back, in words, when one cannot start.
    python_session: str = "auto"
    #: Where a session's commands and results are exchanged: a Unity Catalog volume the app's service
    #: principal can read and write.
    session_volume: str = "/Volumes/workspace/agent_scratch/kernel_sessions"
    session_idle_seconds: int = Field(default=1200, ge=60, le=14400)
    session_max_per_user: int = Field(default=2, ge=1, le=10)
    session_max_total: int = Field(default=3, ge=1, le=50)
    #: Where the app's tool servers reach the app itself. Empty = loopback on the app's own port.
    internal_url: str = ""

    @property
    def production(self) -> bool:
        return self.app_env.strip().lower() in ("production", "prod")


@lru_cache
def settings() -> Settings:
    return Settings()
