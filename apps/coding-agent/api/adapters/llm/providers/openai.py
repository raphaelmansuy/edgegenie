"""OpenAI and OpenAI-compatible endpoints.

The simplest adapter: the Databricks descriptor with a different base URL and a different credential
variable. It is a separate class rather than a row because OpenAI's reasoning models reject
`max_tokens` in favour of `max_completion_tokens`, and that difference must be expressible without
touching the domain (04 §OpenAI).

A proxy base URL is **configuration**, not a secret, which is why it lives on the provider row and a
key lives in the vault. They are different tables for exactly this reason.
"""

from __future__ import annotations

import re

import httpx

from ....config import settings
from ....domain.llm import ModelSpec, ProviderKind, WireProtocol
from ....ports import ProviderDescriptor, Secret
from .base import BaseAdapter

#: Models that reject `max_tokens`. Documented by the vendor; kept as a pattern rather than a list so
#: a new reasoning model needs no code change.
_REASONING = re.compile(r"^(o\d|o\d-|gpt-5|gpt-6)", re.I)


class OpenAIAdapter(BaseAdapter):
    kind = ProviderKind.OPENAI
    wire = WireProtocol.OPENAI
    npm = "@ai-sdk/openai-compatible"

    def base_url(self, spec: ModelSpec, *, host: str = "", project: str = "") -> str:
        base = str(settings().llm_openai_base_url or "").rstrip("/")
        return base or "https://api.openai.com/v1"

    def extra_body(self, spec: ModelSpec) -> dict:
        """`max_tokens` vs `max_completion_tokens`: a reasoning model rejects the old field."""
        if _REASONING.match(spec.endpoint):
            return {"max_completion_tokens": spec.limits.output}
        return {"max_tokens": spec.limits.output}

    async def probe(self, desc: ProviderDescriptor, secret: Secret | None,
                    *, client: httpx.AsyncClient | None = None) -> tuple[str, str]:
        if secret is None:
            return "unauthorised", "no key: add one to use this model"
        url = f"{desc.base_url}/chat/completions"
        payload = {"model": desc.model_key, "messages": [{"role": "user", "content": "ok"}],
                   "max_tokens": 1}
        return await self._post(url, payload, self.auth_headers(secret), client)
