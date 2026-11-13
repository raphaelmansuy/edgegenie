"""Catalogue assembly, resolution and degradation: the service layer, exercised through ports.

Every test here drives the same objects the app builds, with an in-memory store and a fake HTTP layer,
so the precedence rules are asserted without a database or a network.
"""

from __future__ import annotations

import pytest
from api.adapters.llm.providers import adapter_for

from api.adapters.llm.discovery import DiscoveryResult
from api.adapters.llm.store.memory import MemoryRegistryStore
from api.adapters.llm.vault import EnvKek, MemoryVault
from api.domain.llm import (
    Capability,
    CredentialKind,
    CredentialSource,
    Grant,
    LimitEvidence,
    Limits,
    ModelId,
    ModelSpec,
    ModelState,
    ProviderKind,
    UnknownModel,
    WireProtocol,
)
from api.services.credential_service import CredentialService
from api.services.model_resolver import ModelResolver
from api.services.model_service import ModelService, stronger_limits


_LABEL = {
    ProviderKind.DATABRICKS: "Databricks AI Gateway",
    ProviderKind.OPENAI: "OpenAI",
    ProviderKind.ANTHROPIC: "Anthropic",
    ProviderKind.GOOGLE_VERTEX: "Google Vertex AI",
    ProviderKind.FAKE: "The demo agent",
}


def databricks(name: str, endpoint: str | None = None, *, output: int = 8_000,
               evidence: LimitEvidence = LimitEvidence.MEASURED,
               state: ModelState = ModelState.AVAILABLE) -> ModelSpec:
    return ModelSpec(
        id=ModelId(ProviderKind.DATABRICKS, name), display_name=name.replace("databricks-", ""),
        provider_name="Databricks AI Gateway", wire=WireProtocol.SERVING,
        endpoint=endpoint or name, limits=Limits(128_000, output, evidence, "measured"),
        state=state,
    )


def external(model_id: str, *, kind: CredentialKind = CredentialKind.API_KEY) -> ModelSpec:
    mid = ModelId.parse(model_id)
    return ModelSpec(
        id=mid, display_name=mid.name, provider_name=_LABEL[mid.provider],
        wire=WireProtocol.OPENAI if mid.provider is ProviderKind.OPENAI else WireProtocol.VERTEX_NATIVE,
        endpoint=mid.name, limits=Limits(128_000, 16_384, LimitEvidence.DOCUMENTED, "docs"),
        state=ModelState.UNKNOWN, credential_kind=kind,
    )


class FakeDiscovery:
    """A discovery port: the whole point is to control whether it is readable."""

    def __init__(self, specs=None, *, readable: bool = True, outcome: str | None = None) -> None:
        self.specs = specs or []
        self.readable = readable
        self.outcome = outcome or ("ok" if readable else "denied")

    async def fetch(self, token):
        return DiscoveryResult(tuple(self.specs), self.outcome)


async def service(*, specs=(), discovered=None, allow_external=True, grants=None) -> ModelService:
    store = MemoryRegistryStore()
    for spec in specs:
        await store.upsert_model(spec)
    for model_id, grant in (grants or {}).items():
        await store.set_grant(grant)
    return ModelService(store, discovered, default_model="databricks/databricks-llama-4-maverick",
                        allow_external=allow_external, vault=MemoryVault(EnvKek.generate()))


# -- FR-1 / FR-14: discovery adds and never removes ------------------------------------------
async def test_a_model_discovery_reports_appears_without_a_deploy():
    svc = await service(specs=[databricks("databricks-llama-4-maverick")])
    cat = await svc.catalogue("u@example.com")
    assert {m.id.value for m in cat.models} == {"databricks/databricks-llama-4-maverick"}

    svc._discovery = FakeDiscovery([databricks("databricks-llama-4-maverick"),
                                    databricks("databricks-new-model")])
    svc.invalidate()
    cat = await svc.catalogue("u@example.com", refresh=True)
    assert "databricks/databricks-new-model" in {m.id.value for m in cat.models}


async def test_a_model_that_disappears_becomes_not_served_and_is_never_deleted():
    """FR-14 / D8: discovery failing must not revoke access. The row keeps its grants."""
    kept = databricks("databricks-llama-4-maverick")
    svc = await service(specs=[kept], discovered=FakeDiscovery([]))
    cat = await svc.catalogue("u@example.com", refresh=True)
    row = cat.find("databricks/databricks-llama-4-maverick")
    assert row is not None, "the row was deleted"
    assert row.state is ModelState.NOT_SERVED
    assert row.selectable is False


async def test_an_unreadable_discovery_changes_nothing_about_the_catalogue():
    """E-22: `None` means do not filter — the exact rule that kept the first deployment usable."""
    svc = await service(specs=[databricks("databricks-llama-4-maverick")],
                        discovered=FakeDiscovery(readable=False))
    cat = await svc.catalogue("u@example.com", refresh=True)
    row = cat.find("databricks/databricks-llama-4-maverick")
    assert row is not None and row.state is ModelState.AVAILABLE


async def test_a_model_that_comes_back_from_discovery_becomes_available_again():
    svc = await service(specs=[databricks("databricks-llama-4-maverick",
                                          state=ModelState.NOT_SERVED)],
                        discovered=FakeDiscovery([databricks("databricks-llama-4-maverick")]))
    cat = await svc.catalogue("u@example.com", refresh=True)
    assert cat.find("databricks/databricks-llama-4-maverick").state is ModelState.AVAILABLE


# -- precedence: measured beats documented beats default -------------------------------------
def test_a_measured_limit_beats_a_documented_one_and_a_default_never_wins():
    measured = Limits(128_000, 8_000, LimitEvidence.MEASURED, "§3.2")
    documented = Limits(200_000, 30_000, LimitEvidence.DOCUMENTED, "vendor")
    default = Limits(64_000, 4_000, LimitEvidence.DEFAULT, "assumed")
    assert stronger_limits(measured, documented) is measured
    assert stronger_limits(documented, measured) is measured
    assert stronger_limits(default, documented) is documented


async def test_discovery_does_not_downgrade_a_stored_measurement():
    """Discovery knows only existence; it must not replace a measured cap with its own default."""
    svc = await service(specs=[databricks("databricks-llama-4-maverick", output=8_000)],
                        discovered=FakeDiscovery([databricks("databricks-llama-4-maverick",
                                                             output=4_000,
                                                             evidence=LimitEvidence.DEFAULT)]))
    cat = await svc.catalogue("u@example.com", refresh=True)
    row = cat.find("databricks/databricks-llama-4-maverick")
    assert row.limits.output == 8_000
    assert row.limits.evidence is LimitEvidence.MEASURED


# -- health is derived, never static --------------------------------------------------------
async def test_the_newest_health_row_becomes_the_state_with_its_timestamp():
    svc = await service(specs=[external("openai/gpt-4.1")])
    await svc._store.record_health("openai/gpt-4.1", "unauthorised",
                                   "401 Unauthorized: Incorrect API key provided.", source="probe")
    cat = await svc.catalogue("u@example.com", refresh=True)
    row = cat.find("openai/gpt-4.1")
    assert row.state is ModelState.UNAUTHORISED
    assert row.checked_at > 0
    assert "Incorrect API key" in row.detail


# -- grants ---------------------------------------------------------------------------------
async def test_a_model_the_user_was_not_granted_is_not_in_their_catalogue():
    spec = external("openai/gpt-4.1")
    svc = await service(specs=[spec],
                        grants={"openai/gpt-4.1": Grant("openai/gpt-4.1",
                                                        (("user", "vip@example.com", True),))})
    assert await svc.catalogue("vip@example.com", refresh=True) is not None
    theirs = await svc.catalogue("nobody@example.com", refresh=True)
    assert theirs.find("openai/gpt-4.1") is None


# -- C-2: external providers can be switched off entirely ------------------------------------
async def test_external_models_are_hidden_by_policy_and_the_reason_is_stated():
    spec = external("openai/gpt-4.1")
    svc = await service(specs=[spec], allow_external=False)
    cat = await svc.catalogue("u@example.com", refresh=True)
    row = cat.find("openai/gpt-4.1")
    assert row is not None, "hiding is not the same as deleting: the row is still there"
    assert row.selectable is False
    assert "disabled" in row.refusal


# -- C-5 / E-15: degradation ----------------------------------------------------------------
async def test_a_store_that_throws_keeps_serving_the_last_catalogue():
    svc = await service(specs=[databricks("databricks-llama-4-maverick")])
    await svc.catalogue("u@example.com")            # warm the cache and the last-known copy

    async def boom(*_a, **_k):
        raise RuntimeError("connection reset")

    svc._store.models = boom                          # type: ignore[method-assign]
    svc.invalidate()
    cat = await svc.catalogue("u@example.com", refresh=True)
    assert cat.find("databricks/databricks-llama-4-maverick") is not None


# -- the resolver: one path, typed errors ----------------------------------------------------
async def _resolver(specs, vault=None) -> ModelResolver:
    svc = await service(specs=specs)
    return ModelResolver(svc, CredentialService(vault or MemoryVault(EnvKek.generate()), providers=adapter_for), providers=adapter_for)


async def test_the_resolver_returns_a_resolved_model_with_compliant_limits():
    resolver = await _resolver([databricks("databricks-llama-4-maverick")])
    resolved, secret = await resolver.resolve("databricks/databricks-llama-4-maverick",
                                              user_id="u@example.com")
    assert resolved.id.value == "databricks/databricks-llama-4-maverick"
    assert resolved.base_url == "/serving-endpoints"
    assert resolved.output <= resolved.context
    assert secret is None, "a Databricks model needs no provider key of its own"
    assert resolved.env_var == ""


async def test_an_alias_resolves_to_the_model_the_agent_needs():
    resolver = await _resolver([databricks("databricks-gpt-oss-120b")])
    resolved, _ = await resolver.resolve("databricks/system.ai.gpt-oss-120b", user_id="u@example.com")
    assert resolved.endpoint == "databricks-gpt-oss-120b"
    assert resolved.agent_id == "dbx/databricks-gpt-oss-120b"


async def test_an_unknown_model_is_a_typed_error_not_a_plausible_endpoint():
    resolver = await _resolver([])
    with pytest.raises(UnknownModel):
        await resolver.resolve("openai/not-a-real-model", user_id="u@example.com")


async def test_a_model_with_no_key_is_refused_with_the_providers_name():
    from api.domain.llm import NoCredential

    resolver = await _resolver([external("openai/gpt-4.1")])
    with pytest.raises(NoCredential) as caught:
        await resolver.resolve("openai/gpt-4.1", user_id="u@example.com")
    assert "OpenAI" in str(caught.value)


async def test_an_external_model_resolves_with_a_credential_reference_only():
    vault = MemoryVault(EnvKek.generate())
    await vault.put(ProviderKind.OPENAI, "api_key", "sk-" + "a" * 30, user_id="u@example.com")
    resolver = await _resolver([external("openai/gpt-4.1")], vault)
    resolved, secret = await resolver.resolve("openai/gpt-4.1", user_id="u@example.com")
    assert resolved.credential_ref, "the audit record needs a reference"
    assert resolved.credential_source is CredentialSource.USER
    assert secret is None, "the fact must not carry the secret unless a spawn asks for it"
    assert "sk-" not in str(resolved.to_dict())

    _, secret = await resolver.resolve("openai/gpt-4.1", user_id="u@example.com", with_secret=True)
    assert secret is not None and secret.value.startswith("sk-")


async def test_the_env_var_is_the_one_fixed_name_for_every_external_provider():
    """D4: one variable, so one injection mechanism and one thing to audit."""
    vault = MemoryVault(EnvKek.generate())
    await vault.put(ProviderKind.OPENAI, "api_key", "sk-" + "a" * 30, user_id="u@example.com")
    resolver = await _resolver([external("openai/gpt-4.1")], vault)
    resolved, _ = await resolver.resolve("openai/gpt-4.1", user_id="u@example.com")
    assert resolved.env_var == "LLM_PROVIDER_KEY"
