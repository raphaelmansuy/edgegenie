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
    default_model: str = "databricks/system.ai.gpt-oss-120b"
    allowed_models: list[str] = Field(
        default_factory=lambda: [
            "databricks/system.ai.gpt-oss-120b",
            "databricks/databricks-claude-sonnet-4-5",
        ]
    )

    # limits (see specs/001 12 and 15)
    max_concurrent_agents: int = 4
    max_tools: int = 24
    max_turns_per_session: int = 200
    stream_heartbeat_seconds: int = 10

    demo_scenario: str = "notebook"


@lru_cache
def settings() -> Settings:
    return Settings()
