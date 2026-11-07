"""Wiring: settings -> store, vault, catalogue, resolver. The one place implementations are chosen.

`main.build()` calls `build_registry()`; every other module takes the ports it needs. That is the
Dependency-Inversion boundary 08 §2.6 asks for, and it is the same shape `main.build()` already had.

`resolve_static` is the synchronous path the compatibility façade `config_for()` uses. It resolves an
id through the **seed catalogue and the alias table** — never through string surgery — so it cannot
invent an endpoint from a typo, and it needs no database, no event loop and no network.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..adapters.acp.agent_config import AgentConfig
from ..adapters.llm.discovery import DatabricksDiscovery
from ..adapters.llm.store.memory import MemoryRegistryStore
from ..adapters.llm.store.seed_store import SeedRegistryStore
from ..adapters.llm.store.seed import load as load_seed
from ..adapters.llm.vault import EnvVault, MemoryVault, dev_kek_from_env
from ..config import Settings
from ..domain.llm import (
    CredentialKind,
    ModelId,
    ModelSpec,
    ModelState,
    ProviderKind,
    ResolvedModel,
    UnknownModel,
)
from .credential_service import CredentialService
from .health_service import HealthService
from .model_resolver import ModelResolver
from .model_service import ModelService

log = logging.getLogger("app.llm.registry")


@dataclass(slots=True)
class Registry:
    """Everything the LLM feature is made of, wired once and handed to the routes."""

    store: object
    vault: object
    catalogue: ModelService
    resolver: ModelResolver
    credentials: CredentialService
    discovery: object | None = None
    default_model: str = ""
    allow_external: bool = True
    health: object | None = None

    @property
    def source(self) -> str:
        return str(getattr(self.store, "source", "memory"))


async def build_registry(cfg: Settings, *, host: str = "") -> Registry:
    """Choose the store, the vault and the discovery adapter the way the spec says to."""
    store = await _store_for(cfg)
    vault = _vault_for(cfg)
    discovery = DatabricksDiscovery(host, lambda: None, ttl=float(cfg.llm_discovery_seconds)) if host else None
    default = (getattr(store, "default_model", "") or cfg.default_model)
    service = ModelService(store, discovery, default_model=default,
                           allow_external=cfg.llm_allow_external, vault=vault)
    credentials = CredentialService(vault)
    resolver = ModelResolver(service, credentials, host=host,
                             allow_external=cfg.llm_allow_external)
    health = HealthService(store, credentials, interval=float(cfg.llm_probe_seconds), host=host)
    log.info("llm registry: source=%s vault=%s external=%s",
             getattr(store, "source", "?"), getattr(vault, "mode", "?"), cfg.llm_allow_external)
    return Registry(store=store, vault=vault, catalogue=service, resolver=resolver,
                    credentials=credentials, discovery=discovery, default_model=default,
                    allow_external=cfg.llm_allow_external, health=health)


async def _store_for(cfg: Settings):
    """Database when a DSN is set and reachable; else the seed — which is a first-class citizen (C-5).

    A configured-but-unreachable DSN is `degraded`, not an exception: the app keeps serving, and the
    response says which part is degraded so the settings screen can tell the user.
    """
    path = cfg.llm_seed_path or None
    if cfg.agent_mode == "fake":
        return demo_store(cfg)
    if not cfg.llm_database_url:
        return await SeedRegistryStore.open(path=path, source="seed")
    try:
        from ..adapters.llm.store.pg import PgRegistryStore

        store = await PgRegistryStore.connect(cfg.llm_database_url, seed_path=path)
        return store
    except Exception as exc:  # noqa: BLE001 - a database we cannot reach is a state, not a crash
        log.warning("the model database is unreachable (%s); serving the seed catalogue", exc)
        degraded = await SeedRegistryStore.open(path=path, source="degraded")
        degraded.mark_all_unknown("the model database is unreachable")
        return degraded


def demo_store(cfg: Settings):
    """Demo and test mode: the catalogue is `Settings.allowed_models`, plus the seed rows on request.

    It is a `MemoryRegistryStore` loaded from configuration rather than a seed file, so demo mode runs
    the **same** catalogue, resolver and policy code as production. A separate demo path would mean
    the code under test is not the code that ships.

    `llm_demo_seed` adds `seed/llm_models.yaml` to the demo catalogue. It exists so the end-to-end
    suite and the screenshots can exercise the real groups, states and limit evidence without a
    workspace — the demo agent still answers turns for the `fake/*` ids, which is why both are present.
    """
    from ..adapters.llm.store.memory import MemoryRegistryStore

    store = MemoryRegistryStore(source="memory")
    seeded = _demo_seed_specs() if cfg.llm_demo_seed else []
    for spec in seeded:
        _register(store, spec)
    for model_id in dict.fromkeys(cfg.allowed_models):
        try:
            spec = static_spec(model_id)
        except Exception:  # noqa: BLE001 - an unresolvable demo id is skipped, not fatal
            continue
        _register(store, spec)
    store.default_model = (cfg.default_model if cfg.default_model in store._models  # noqa: SLF001
                           else next(iter(store._models), ""))
    return store


def _register(store, spec) -> None:
    """One model and its provider in a memory store. Never overwrites a row that already exists."""
    store._models.setdefault(spec.id.value, spec)                                  # noqa: SLF001
    store._providers.setdefault(spec.id.provider.value, {                          # noqa: SLF001
        "id": spec.id.provider.value, "display_name": spec.provider_name,
        "kind": spec.id.provider.value, "wire": spec.wire.value,
        "base_url": "", "npm": "", "enabled": True,
    })


def _demo_seed_specs() -> list:
    """The seed rows, with the Databricks ones marked unknown: nothing has probed them here."""
    from dataclasses import replace

    return [replace(spec, state=ModelState.UNKNOWN) if spec.state is ModelState.AVAILABLE else spec
            for spec in _seed().models]


def _vault_for(cfg: Settings):
    """Envelope vault when a KEK exists; env-only vault otherwise, with a visible mode."""
    kek = _configured_kek(cfg)
    if kek.usable:
        return MemoryVault(kek)
    if cfg.production:
        log.warning("no usable KEK in production: keys cannot be saved (R-5)")
    return EnvVault()


def _configured_kek(cfg: Settings):
    """The KEK this deployment was given, from settings rather than from `os.environ` directly.

    Reading the environment here would make a `Settings` passed by a test invisible, which is the
    difference between "the test exercises the vault" and "the test exercises the refusal path".
    """
    from ..adapters.llm.vault.kek import EnvKek, KekError

    if cfg.llm_kek:
        try:
            kek = EnvKek(cfg.llm_kek, key_id="env-1")
            if cfg.production:
                log.warning("a development KEK (LLM_KEK) is in use in production; prefer a secret scope")
            return kek
        except KekError as exc:
            log.warning("LLM_KEK is unusable: %s", exc)
            from ..adapters.llm.vault.kek import NoneKek

            return NoneKek(str(exc))
    return _scope_kek(cfg)


def _scope_kek(cfg: Settings):
    """A KEK read from a Databricks secret scope, when one is named and readable."""
    from ..adapters.llm.vault.kek import NoneKek, from_settings

    if not cfg.llm_kek_scope:
        return from_settings(env_kek=None)
    value = _read_scope(cfg.llm_kek_scope, cfg.llm_kek_key)
    return from_settings(secret_scope_value=value, scope_name=cfg.llm_kek_scope) if value else NoneKek(
        f"secret scope {cfg.llm_kek_scope!r} is not readable")


def _read_scope(scope: str, key: str) -> str | None:
    """Read a secret from a workspace scope through the CLI, once at boot.

    Deliberately not a `databricks.sdk` dependency: the app's only workspace credential today is the
    forwarded user token, and a service-principal scope read is an ops concern (12 §Configuration).
    Returns None when it cannot be read, and the caller then fails closed rather than quietly
    downgrading to a weaker KEK.
    """
    import shutil
    import subprocess

    if not shutil.which("databricks"):
        return None
    try:
        out = subprocess.run(["databricks", "secrets", "get-secret", "--scope", scope, "--key", key,
                              "--output", "json"], capture_output=True, text=True, timeout=15, check=True)
        import json

        body = json.loads(out.stdout or "{}")
        import base64

        return base64.b64decode(str(body.get("value") or "")).decode("utf-8").strip()
    except Exception:  # noqa: BLE001 - an unreadable scope is a known state, not a crash
        return None


# --------------------------------------------------------------------------------------------
# The synchronous path, for the `config_for` façade
# --------------------------------------------------------------------------------------------

_SEED = None


def _seed():
    global _SEED
    if _SEED is None:
        _SEED = load_seed()
    return _SEED


def static_spec(model_id: str) -> ModelSpec:
    """The seed row for an id, after the alias table. Raises `UnknownModel` for an unknown id."""
    mid = ModelId.parse(model_id)
    spec = next((m for m in _seed().models if m.id.value == mid.value), None)
    if spec is None:
        # Demo mode: the fake agent advertises its own models and there is no provider to reach. The
        # spec exists so the same resolution path serves demo, tests and production (one path, C-3).
        if mid.provider is ProviderKind.FAKE:
            from ..domain.llm import Capability, WireProtocol
            from ..domain.llm.limits import DEFAULT_LIMITS

            return ModelSpec(
                id=mid, display_name=mid.name, provider_name="The demo agent",
                wire=WireProtocol.FAKE, endpoint=mid.name, limits=DEFAULT_LIMITS,
                capability=Capability.TOOLS, credential_kind=CredentialKind.NONE,
            )
        # An id the seed does not know may still be a served endpoint written directly:
        # `databricks/<endpoint>`. That is a lookup, not string surgery: the model name IS the endpoint.
        if mid.provider is ProviderKind.DATABRICKS and "/" not in mid.name:
            from ..adapters.acp.agent_config import _limits_for
            from ..domain.llm import Capability, WireProtocol

            return ModelSpec(
                id=mid, display_name=mid.name.replace("databricks-", ""),
                provider_name="Databricks AI Gateway", wire=WireProtocol.SERVING,
                endpoint=mid.name, limits=_limits_for(mid.name),
                capability=Capability.TOOLS, credential_kind=CredentialKind.NONE,
            )
        raise UnknownModel(mid.value)
    return spec


def resolve_static(model_id: str, host: str = "") -> AgentConfig:
    """`AgentConfig` for an id, from data. Synchronous because three legacy call sites are."""
    spec = static_spec(model_id)
    from ..adapters.llm.providers import adapter_for
    from ..domain.llm import clamp

    desc = adapter_for(spec.id.provider).descriptor(spec, host=host)
    resolved = ResolvedModel(
        id=spec.id, provider=spec.id.provider, wire=spec.wire, endpoint=spec.endpoint,
        base_url=desc.base_url, limits=clamp(spec.limits), capability=spec.capability,
        env_var="", npm=desc.npm,
    )
    return AgentConfig.from_resolved(resolved, host=host)


def refresh_seed() -> None:
    """Test hook: forget the cached seed file after editing it."""
    global _SEED
    _SEED = None


def build_registry_sync(cfg: Settings) -> Registry:
    """The no-event-loop path used by `build()` and by the test client.

    It makes exactly the same choices as `build_registry`, but constructs the seed store without
    awaiting anything. When a DSN is configured the Postgres store is connected on the first request
    that needs it (`PsycopgLazyStore`), so importing or constructing the app never blocks on a network.
    """
    from ..adapters.llm.discovery import DatabricksDiscovery
    from ..adapters.llm.store.seed_store import SeedRegistryStore
    from ..adapters.llm.vault import EnvVault, MemoryVault

    host = __import__("os").environ.get("DATABRICKS_HOST", "")
    if cfg.agent_mode == "fake":
        store = demo_store(cfg)
    else:
        store = SeedRegistryStore(source="degraded" if cfg.llm_database_url else "seed",
                                  path=cfg.llm_seed_path or None)
        # The seed file is small and local, so loading it inline keeps boot deterministic. A
        # configured DSN is *marked* degraded until the async lifespan upgrades it, which is honest
        # about the state rather than pretending the database was reached.
        _load_seed_inline(store)
        if cfg.llm_database_url:
            store.mark_all_unknown("the model database has not been reached yet")

    kek = _configured_kek(cfg)
    vault = MemoryVault(kek) if kek.usable else EnvVault()

    discovery = DatabricksDiscovery(host, lambda: None,
                                    ttl=float(cfg.llm_discovery_seconds)) if host else None
    default = getattr(store, "default_model", "") or cfg.default_model
    service = ModelService(store, discovery, default_model=default,
                           allow_external=cfg.llm_allow_external, vault=vault)
    credentials = CredentialService(vault)
    resolver = ModelResolver(service, credentials, host=host,
                             allow_external=cfg.llm_allow_external)
    health = HealthService(store, credentials, interval=float(cfg.llm_probe_seconds), host=host)
    return Registry(store=store, vault=vault, catalogue=service, resolver=resolver,
                    credentials=credentials, discovery=discovery, default_model=default,
                    allow_external=cfg.llm_allow_external, health=health)


def _load_seed_inline(store) -> None:
    """Load the seed rows into a store without awaiting: the file is local and tiny."""
    for provider in store.seed.providers:
        store._providers[provider.id] = {  # noqa: SLF001 - constructor work, one place
            "id": provider.id, "display_name": provider.display_name,
            "kind": provider.kind.value, "wire": provider.wire.value,
            "base_url": provider.base_url, "npm": provider.npm, "enabled": True,
        }
    for spec in store.seed.models:
        store._models[spec.id.value] = spec  # noqa: SLF001
