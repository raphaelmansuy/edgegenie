"""Anthropic messages: `x-api-key` plus a version header, and one flag everyone forgets.

`toolStreaming: false` is not optional. With it on, tool calls arrive in a shape this agent's mapper
does not reassemble; the documented Databricks configuration turns it off
(`docs/genie-code-replacement-spec.md` §7.2). The adapter sets it here, and a model row may override
it, so the trap is data with a measured default rather than folklore in a comment.
"""

from __future__ import annotations

import httpx

from ....config import settings
from ....domain.llm import ModelSpec, ProviderKind, WireProtocol
from ....ports import ProviderDescriptor, Secret
from .base import BaseAdapter

#: Pinned, not floating: a version header that moves under us changes the wire without a deploy.
ANTHROPIC_VERSION = "2023-06-01"


class AnthropicAdapter(BaseAdapter):
    kind = ProviderKind.ANTHROPIC
    wire = WireProtocol.ANTHROPIC
    npm = "@ai-sdk/anthropic"
    bearer = False

    def base_url(self, spec: ModelSpec, *, host: str = "", project: str = "") -> str:
        base = str(settings().llm_anthropic_base_url or "").rstrip("/")
        return base or "https://api.anthropic.com/v1"

    def tool_streaming(self, spec: ModelSpec) -> bool:
        """Off by default for this wire: the measured trap, not a preference."""
        return False

    def headers(self, spec: ModelSpec) -> dict[str, str]:
        return {"anthropic-version": ANTHROPIC_VERSION}

    def auth_headers(self, secret: Secret | None) -> dict[str, str]:
        if secret is None:
            return {"anthropic-version": ANTHROPIC_VERSION}
        return {"x-api-key": secret.value, "anthropic-version": ANTHROPIC_VERSION}

    async def probe(self, desc: ProviderDescriptor, secret: Secret | None,
                    *, client: httpx.AsyncClient | None = None) -> tuple[str, str]:
        if secret is None:
            return "unauthorised", "no key: add one to use this model"
        url = f"{desc.base_url}/messages"
        payload = {"model": desc.model_key, "max_tokens": 1,
                   "messages": [{"role": "user", "content": "ok"}]}
        return await self._post(url, payload, self.auth_headers(secret), client)
