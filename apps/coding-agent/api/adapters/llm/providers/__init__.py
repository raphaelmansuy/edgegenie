"""Provider adapters: one per wire protocol, behind one interface.

The domain never names a vendor (Axiom A2, CI gate C-2). Each adapter answers three questions —
where the model lives, what the credential variable is called, and whether it answers — and nothing
else. `descriptor()` is pure, so the URL logic is unit-testable without a network.

`registry()` is the one place a kind becomes a class, so adding a provider is one line here plus one
adapter module — and the CI rule fails if a vendor name appears in `api/domain`.
"""

from __future__ import annotations

from ....domain.llm import ProviderKind
from .anthropic import AnthropicAdapter
from .base import BaseAdapter
from .databricks import DatabricksAdapter
from .fake import FakeAdapter
from .openai import OpenAIAdapter
from .vertex import VertexAdapter

__all__ = [
    "AnthropicAdapter",
    "BaseAdapter",
    "DatabricksAdapter",
    "OpenAIAdapter",
    "VertexAdapter",
    "adapter_for",
    "registry",
]

_ADAPTERS: tuple[type[BaseAdapter], ...] = (
    DatabricksAdapter,
    FakeAdapter,
    OpenAIAdapter,
    AnthropicAdapter,
    VertexAdapter,
)


def registry() -> dict[ProviderKind, BaseAdapter]:
    """One instance per kind. Instances are stateless, so sharing them is safe."""
    return {cls.kind: cls() for cls in _ADAPTERS}


def adapter_for(kind: ProviderKind) -> BaseAdapter:
    """Raises `KeyError` for a kind with no adapter — a validation failure, not a call-time one."""
    try:
        return _BY_KIND[kind]
    except KeyError:
        raise KeyError(f"no provider adapter for {kind.value}") from None


_BY_KIND: dict[ProviderKind, BaseAdapter] = {cls.kind: cls() for cls in _ADAPTERS}
