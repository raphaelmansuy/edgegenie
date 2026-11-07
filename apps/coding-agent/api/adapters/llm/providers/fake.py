"""The demo provider: no wire, no credential, no network.

It is an adapter rather than a special case in the resolver because demo mode must exercise **the
same** resolution path as production — that is the whole point of C-3. A branch in the resolver for
"mode == fake" would mean the path under test is not the path that ships.

Its descriptor is inert on purpose: the fake agent replays a recorded turn, so there is no URL to
reach. Anything that tries to probe it gets `unknown`, which is the honest answer.
"""

from __future__ import annotations

from ....domain.llm import ModelSpec, ProviderKind, WireProtocol
from ....ports import ProviderDescriptor
from .base import BaseAdapter


class FakeAdapter(BaseAdapter):
    kind = ProviderKind.FAKE
    wire = WireProtocol.FAKE
    npm = ""

    def base_url(self, spec: ModelSpec, *, host: str = "", project: str = "") -> str:
        return ""

    def env_var(self, spec: ModelSpec) -> str:
        return ""

    def descriptor(self, spec: ModelSpec, *, host: str = "", project: str = "") -> ProviderDescriptor:
        return ProviderDescriptor(kind=self.kind, wire=WireProtocol.FAKE, base_url="", npm="",
                                  model_key=spec.endpoint, tool_streaming=True)

    async def probe(self, desc: ProviderDescriptor, secret=None, *, client=None) -> tuple[str, str]:
        """A replay has no endpoint to reach, so nothing can be proven about it."""
        return "unknown", ""
