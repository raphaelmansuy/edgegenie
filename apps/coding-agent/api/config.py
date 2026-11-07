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

    # tools
    tool_mode: Literal["none", "subprocess"] = "none"
    tool_server_python: str = "python3"

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
    #: Demo mode only: add the seed catalogue to `allowed_models`, so the picker's groups, states and
    #: limit evidence can be exercised (and screenshotted) without a workspace. The e2e suite sets it.
    llm_demo_seed: bool = False

    # limits (see specs/001 12 and 15)
    max_concurrent_agents: int = 4
    max_tools: int = 24
    max_turns_per_session: int = 200
    stream_heartbeat_seconds: int = 10

    demo_scenario: str = "notebook"

    @property
    def production(self) -> bool:
        return self.app_env.strip().lower() in ("production", "prod")


@lru_cache
def settings() -> Settings:
    return Settings()
