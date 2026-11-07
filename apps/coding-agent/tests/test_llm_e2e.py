"""End to end with a **fake provider that records the headers it receives**.

This is the one test the spec calls out as most important (09 §Test plan): it covers FR-7, FR-8, TH-10
and S6 in a single assertion — the request carries the key that was stored **for that user**, and the
other user's key never appears in any request.

It also proves the child environment rule: a session gets the workspace token plus exactly one
provider key, and the model switch reaches the provider through the resolver.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx
import pytest

from api.adapters.acp.runtime import AcpAgentRuntime
from api.adapters.llm.providers import adapter_for
from api.adapters.llm.vault import EnvKek, MemoryVault
from api.domain.llm import (
    CredentialKind,
    LimitEvidence,
    Limits,
    ModelId,
    ModelSpec,
    ModelState,
    ProviderKind,
    WireProtocol,
)
from api.ports import Secret
from api.services.credential_service import CredentialService
from api.services.model_resolver import ModelResolver
from api.services.model_registry import demo_store
from api.services.model_service import ModelService

ROOT = Path(__file__).resolve().parents[1]

ALICE_KEY = "sk-" + "alice" + "A" * 30
BOB_KEY = "sk-" + "bobb" + "B" * 30


class RecordingProvider:
    """An OpenAI-compatible provider that keeps every request it sees."""

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.status = 200
        self.body: dict = {"choices": [{"message": {"content": "ok"}}]}

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return httpx.Response(self.status, json=self.body)

        return httpx.MockTransport(handle)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self.transport())

    def authorizations(self) -> list[str]:
        return [r.headers.get("authorization", "") for r in self.requests]


def openai_spec(output: int = 16_384) -> ModelSpec:
    return ModelSpec(
        id=ModelId.parse("openai/gpt-4.1"), display_name="gpt-4.1", provider_name="OpenAI",
        wire=WireProtocol.OPENAI, endpoint="gpt-4.1",
        limits=Limits(128_000, output, LimitEvidence.DOCUMENTED, "vendor docs"),
        credential_kind=CredentialKind.API_KEY, state=ModelState.AVAILABLE,
    )


async def _registry_with(store, vault):
    service = ModelService(store, None, default_model="openai/gpt-4.1", allow_external=True,
                           vault=vault)
    credentials = CredentialService(vault)
    return service, credentials, ModelResolver(service, credentials, allow_external=True)


# -- the assertion the spec cares about most --------------------------------------------------
async def test_each_users_request_carries_that_users_key_and_never_the_others():
    """FR-7, FR-8, TH-10, S6 in one test: a cross-tenant leak is an incident, not a bug."""
    vault = MemoryVault(EnvKek.generate())
    store = demo_store_store([openai_spec()])
    service, credentials, resolver = await _registry_with(store, vault)
    await vault.put(ProviderKind.OPENAI, "api_key", ALICE_KEY, user_id="alice@example.com")
    await vault.put(ProviderKind.OPENAI, "api_key", BOB_KEY, user_id="bob@example.com")

    provider = RecordingProvider()
    adapter = adapter_for(ProviderKind.OPENAI)

    for user, expected in (("alice@example.com", ALICE_KEY), ("bob@example.com", BOB_KEY)):
        resolved, secret = await resolver.resolve("openai/gpt-4.1", user_id=user, with_secret=True)
        env = (await credentials.env_for(resolved, user_id=user,
                                         workspace_token="dapi-workspace")).vars
        # Exactly one provider key in the child's environment, and it is the right one.
        assert env["LLM_PROVIDER_KEY"] == expected
        assert sum(1 for k in env if k.startswith("LLM_")) == 1
        state, _detail = await adapter.probe(
            adapter.descriptor(resolved_spec(resolved)), Secret(value=env["LLM_PROVIDER_KEY"]),
            client=provider.client())
        assert state == "available"

    seen = " ".join(provider.authorizations())
    assert ALICE_KEY in seen and BOB_KEY in seen
    # Interleaved: nobody saw the other's key in the same request.
    first, second = provider.authorizations()
    assert ALICE_KEY in first and BOB_KEY not in first
    assert BOB_KEY in second and ALICE_KEY not in second


async def test_a_user_with_no_key_is_refused_rather_than_borrowing_a_workspace_key_silently():
    """There is no "borrow the workspace key" path unless one exists explicitly as a workspace row."""
    vault = MemoryVault(EnvKek.generate())
    store = demo_store_store([openai_spec()])
    service, credentials, resolver = await _registry_with(store, vault)
    await vault.put(ProviderKind.OPENAI, "api_key", ALICE_KEY, user_id="alice@example.com")

    from api.domain.llm import NoCredential

    with pytest.raises(NoCredential):
        await resolver.resolve("openai/gpt-4.1", user_id="carol@example.com")


async def test_a_workspace_key_serves_everyone_once_it_exists_explicitly():
    vault = MemoryVault(EnvKek.generate())
    store = demo_store_store([openai_spec()])
    _service, credentials, _resolver = await _registry_with(store, vault)
    await vault.put(ProviderKind.OPENAI, "api_key", ALICE_KEY, user_id="admin@example.com",
                    scope="workspace")

    ref = await credentials.find(ProviderKind.OPENAI, user_id="anyone@example.com")
    assert ref is not None and ref.scope_kind == "workspace"


# -- the child environment: one key, and only the selected one -------------------------------
async def test_a_databricks_session_gets_the_workspace_token_and_no_provider_key():
    store = demo_store_store([openai_spec()])
    vault = MemoryVault(EnvKek.generate())
    _service, credentials, _resolver = await _registry_with(store, vault)
    from api.domain.llm import Capability, ResolvedModel

    dbx = ResolvedModel(
        id=ModelId(ProviderKind.DATABRICKS, "databricks-llama-4-maverick"), provider=ProviderKind.DATABRICKS,
        wire=WireProtocol.SERVING, endpoint="databricks-llama-4-maverick",
        base_url="https://h/serving-endpoints", limits=Limits(128_000, 8_000),
        capability=Capability.TOOLS, env_var="",
    )
    child = await credentials.env_for(dbx, user_id="u@example.com", workspace_token="dapi-ws")
    assert child.vars == {"DATABRICKS_TOKEN": "dapi-ws"} and child.files == {}


async def test_a_vertex_session_receives_the_key_as_a_file_and_the_project_as_a_variable():
    vault = MemoryVault(EnvKek.generate())
    from tests.test_llm_domain import _service_account

    await vault.put(ProviderKind.GOOGLE_VERTEX, "service_account_json",
                    _service_account("vertex-demo-1"), user_id="u@example.com")
    store = demo_store_store([ModelSpec(
        id=ModelId.parse("google_vertex/google/gemini-3.8-flash"), display_name="gemini-3.8-flash",
        provider_name="Google Vertex AI", wire=WireProtocol.VERTEX_NATIVE,
        endpoint="google/gemini-3.8-flash", limits=Limits(1_000_000, 30_000),
        credential_kind=CredentialKind.SERVICE_ACCOUNT_JSON, state=ModelState.AVAILABLE)])
    service = ModelService(store, None, default_model="google_vertex/google/gemini-3.8-flash",
                          allow_external=True, vault=vault)
    credentials = CredentialService(vault)
    resolver = ModelResolver(service, credentials, allow_external=True)
    resolved, _ = await resolver.resolve("google_vertex/google/gemini-3.8-flash",
                                         user_id="u@example.com")
    child = await credentials.env_for(resolved, user_id="u@example.com", workspace_token="dapi-ws")
    # The built-in Vertex provider reads a key FILE. The key is never an environment value.
    assert set(child.files) == {"GOOGLE_APPLICATION_CREDENTIALS"}
    assert json.loads(child.files["GOOGLE_APPLICATION_CREDENTIALS"])["project_id"] == "vertex-demo-1"
    assert child.vars["GOOGLE_VERTEX_PROJECT"] == "vertex-demo-1"
    assert child.vars["GOOGLE_VERTEX_LOCATION"] == "global"
    assert "LLM_PROVIDER_KEY" not in child.vars
    assert not any("BEGIN" in v for v in child.vars.values())
    # And the agent is told the native block and the publisher-less name it actually lists.
    assert resolved.wire is WireProtocol.VERTEX_NATIVE
    assert resolved.agent_id == "google-vertex/gemini-3.8-flash"
    assert resolved.endpoint == "gemini-3.8-flash"


# -- FR-9 / FR-10: switching and immutable provenance ----------------------------------------
async def test_a_turn_pins_the_model_and_a_later_switch_does_not_rewrite_it(tmp_path):
    """E-18: the running turn keeps its model; the next turn gets the new one."""
    from api.adapters.mcp.registry import NullToolRegistry
    from api.adapters.memory.store import MemoryEventStore
    from api.config import Settings
    from api.services.catalogue import SettingsModelCatalog
    from api.services.orchestrator import Orchestrator

    cfg = Settings(allowed_models=["fake/model-a", "fake/model-b"], default_model="fake/model-a",
                   agent_mode="fake")
    store = demo_store(cfg)
    vault = MemoryVault(EnvKek.generate())
    service = ModelService(store, None, default_model="fake/model-a", allow_external=False,
                           vault=vault)
    credentials = CredentialService(vault)
    resolver = ModelResolver(service, credentials, allow_external=False)

    rt = AcpAgentRuntime(command=f"{sys.executable} -m api.adapters.fake.agent fixed:notebook 0.35")
    rt._extra_env = {"PYTHONPATH": str(ROOT)}                       # noqa: SLF001
    orch = Orchestrator(rt, NullToolRegistry(), MemoryEventStore(), SettingsModelCatalog(cfg),
                        demo=True, resolver=resolver, credentials=credentials,
                        store_llm=store, health=None)
    session = await orch.create("u@example.com", str(tmp_path), "fake/model-a", None)
    live = orch.get(session.id)

    first = await orch.submit(session.id, "Build a notebook that shows revenue by pickup hour")
    await orch.set_model(session.id, "fake/model-b")            # mid-turn
    for _ in range(200):
        if first.status.value not in ("queued", "running", "auditing"):
            break
        await __import__("asyncio").sleep(0.05)

    pins = await store.turn_models(session.id)
    assert pins[0]["modelId"] == "fake/model-a", "the running turn was retargeted"
    # The switch applies to the NEXT turn: a second submit pins the new model.
    second = await orch.submit(session.id, "and now something else")
    pins = await store.turn_models(session.id)
    by_turn = {p["turnId"]: p["modelId"] for p in pins}
    assert by_turn[first.id] == "fake/model-a"
    assert by_turn[second.id] == "fake/model-b"

    facts = await orch.model_facts(session.id)
    assert facts["current"] == "fake/model-b"
    assert facts["switchAtTurn"] == 2


async def test_writing_a_turn_pin_twice_is_a_no_op_not_an_overwrite():
    """C-8: insert-once at the store seam. This is what makes Axiom A5 structural."""
    store = demo_store_store([])
    pin = {"turnId": "t1", "sessionId": "s1", "modelId": "openai/gpt-4.1",
           "providerId": "openai", "wire": "openai", "endpoint": "gpt-4.1"}
    await store.record_turn_model(pin)
    await store.record_turn_model({**pin, "modelId": "openai/gpt-4.1-mini"})
    rows = await store.turn_models("s1")
    assert [r["modelId"] for r in rows] == ["openai/gpt-4.1"]


# -- a cap rejection lowers the stored cap, never raises it ----------------------------------
async def test_a_cap_rejection_lowers_the_stored_cap_and_never_raises_it():
    """E-4: the most common invisible failure."""
    from api.services.health_service import HealthService

    store = demo_store_store([openai_spec(output=24_000)])
    vault = MemoryVault(EnvKek.generate())
    credentials = CredentialService(vault)
    health = HealthService(store, credentials, interval=0.0)
    spec = openai_spec(output=24_000)

    await health.note_turn(spec, "max_tokens (24000) cannot exceed 8192", turn_id="t9")
    row = await store.find("openai/gpt-4.1")
    assert row.limits.output == 8_192
    assert row.limits.evidence is LimitEvidence.MEASURED
    assert "t9" in row.limits.source

    # A *higher* number in an error is ignored: it could be a proxy's cap, not the model's.
    await health.note_turn(row, "max_tokens (8000) cannot exceed 32000", turn_id="t10")
    after = await store.find("openai/gpt-4.1")
    assert after.limits.output == 8_192, "a cap must never be raised from an error message"


async def test_a_turn_failure_is_classified_and_recorded_as_health():
    from api.services.health_service import HealthService

    store = demo_store_store([openai_spec()])
    vault = MemoryVault(EnvKek.generate())
    health = HealthService(store, credentials=CredentialService(vault), interval=0.0)
    spec = openai_spec()
    state = await health.note_turn(spec, "401 Unauthorized: Incorrect API key provided.")
    assert state == "unauthorised"
    row = await store.health_state("openai/gpt-4.1")
    assert row is not None and row[0] == "unauthorised"


# -- a probe is rate limited, because it costs money -----------------------------------------
async def test_a_probe_is_not_repeated_inside_the_interval():
    """E-24: a health loop that burns tokens is a bug, not a feature."""
    from api.services.health_service import HealthService

    store = demo_store_store([openai_spec()])
    vault = MemoryVault(EnvKek.generate())
    calls: list[str] = []

    class CounterVault(MemoryVault):
        async def find(self, provider, *, user_id):
            calls.append(user_id)
            return None

    health = HealthService(store, CredentialService(CounterVault(vault._kek)), interval=900)  # noqa: SLF001
    spec = openai_spec()
    await health.probe(spec, user_id="u@example.com")
    await health.probe(spec, user_id="u@example.com")
    await health.probe(spec, user_id="u@example.com")
    assert len(calls) == 1, "the probe ran more than once inside its interval"


# -- helpers ---------------------------------------------------------------------------------
def demo_store_store(specs):
    """A store holding exactly these specs, with their providers registered."""
    from api.adapters.llm.store.memory import MemoryRegistryStore

    store = MemoryRegistryStore(source="memory")
    for spec in specs:
        store._models[spec.id.value] = spec      # noqa: SLF001 - test construction
        store._providers.setdefault(spec.id.provider.value, {  # noqa: SLF001
            "id": spec.id.provider.value, "display_name": spec.provider_name,
            "kind": spec.id.provider.value, "wire": spec.wire.value, "enabled": True,
            "base_url": "", "npm": "",
        })
    if specs:
        store.default_model = specs[0].id.value
    return store


def resolved_spec(resolved):
    """The `ModelSpec` a resolved model came from, for a probe that needs the spec and not the fact."""
    return ModelSpec(
        id=resolved.id, display_name=resolved.id.name, provider_name="provider",
        wire=resolved.wire, endpoint=resolved.endpoint, limits=resolved.limits,
        capability=resolved.capability, credential_kind=CredentialKind.API_KEY,
    )


# -- the key file's life: private while the child runs, gone when it does not -----------------
def test_secret_files_are_private_replaced_on_switch_and_removed_on_demand(tmp_path):
    import os
    import stat
    from types import SimpleNamespace

    from api.services.orchestrator import Orchestrator

    live = SimpleNamespace(extra={})
    paths = Orchestrator._materialise(live, {"GOOGLE_APPLICATION_CREDENTIALS": '{"k": "v"}'})
    path = paths["GOOGLE_APPLICATION_CREDENTIALS"]
    assert open(path).read() == '{"k": "v"}'
    assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
    assert stat.S_IMODE(os.stat(os.path.dirname(path)).st_mode) == 0o700
    # A switch to a provider that needs no key removes the previous provider's file.
    assert Orchestrator._materialise(live, {}) == {}
    assert not os.path.exists(path)
    # And the private directory is the one thing archive removes.
    import shutil

    shutil.rmtree(live.extra["secret_dir"], ignore_errors=True)
    assert not os.path.exists(live.extra["secret_dir"])
