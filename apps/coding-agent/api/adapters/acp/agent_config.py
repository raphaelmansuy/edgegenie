"""Compatibility exports; configuration rules have one pure implementation in the domain."""
from ...domain.llm.agent_config import *  # noqa: F401,F403
from ...domain.llm.agent_config import _limits_for

def config_for(model_id: str, host: str) -> AgentConfig:
    """Compatibility façade: an id -> `AgentConfig`, through the catalogue, never through the id.

    One definition, delegating to the same pure resolution the resolver uses (C-3). It is kept only
    until the last call site is gone (P7), and `tests/test_llm_agent_config.py` counts definitions.
    """
    from ...composition.model_registry import resolve_static

    return resolve_static(model_id, host)
