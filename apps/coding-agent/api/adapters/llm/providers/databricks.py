"""Databricks AI Gateway: serving endpoints, the workspace token, and per-endpoint caps.

**Status: working today** — this adapter reproduces `agent_config.py`'s behaviour byte for byte, which
is the golden-file test that makes the whole refactor safe: if the Databricks config changes by one
byte, the exam results in this repository stop being comparable (10 §Backward compatibility).

Two traps live here and nowhere else:

* the base URL is `{host}/serving-endpoints`, with the host normalised once;
* the model key is the serving-endpoint name, not the foundation-model name the gateway advertises —
  which is why the alias map exists.
"""

from __future__ import annotations

import httpx

from ....domain.llm import ModelSpec, ProviderKind, WireProtocol
from ....ports import ProviderDescriptor, Secret
from ...databricks.http import normalize_host
from .base import WORKSPACE_TOKEN_ENV, BaseAdapter

GATEWAY_PATH = "/serving-endpoints"
#: The chat-completions suffix the gateway exposes beneath a serving endpoint.
CHAT_PATH = "/chat/completions"


class DatabricksAdapter(BaseAdapter):
    kind = ProviderKind.DATABRICKS
    wire = WireProtocol.SERVING
    npm = "@ai-sdk/openai-compatible"

    def base_url(self, spec: ModelSpec, *, host: str = "", project: str = "") -> str:
        base = normalize_host(host) if host else ""
        return f"{base.rstrip('/')}{GATEWAY_PATH}" if base else GATEWAY_PATH

    def env_var(self, spec: ModelSpec) -> str:
        """The workspace token. There is no key to manage for a gateway model (FR-8 aside)."""
        return WORKSPACE_TOKEN_ENV

    async def probe(self, desc: ProviderDescriptor, secret: Secret | None,
                    *, client: httpx.AsyncClient | None = None) -> tuple[str, str]:
        if secret is None:
            return "unauthorised", "no Databricks token: the workspace connection is unavailable"
        url = f"{desc.base_url}/{desc.model_key}{CHAT_PATH}"
        payload = {"messages": [{"role": "user", "content": "ok"}], "max_tokens": 1}
        return await self._post(url, payload, {"Authorization": f"Bearer {secret.value}"}, client)
