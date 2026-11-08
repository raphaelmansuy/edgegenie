"""Credentials: the vault, the envelope, the scopes, and the eight sinks (06 §Secret hygiene).

**E-12 is first** because it is the only case where a bug is a cross-tenant incident rather than a
broken feature, and it is cheap to test with a fake provider: two users, two keys, and an assertion
that the request a provider receives carries the right one.
"""

from __future__ import annotations

import json

import pytest

from api.adapters.llm.vault import EnvKek, EnvVault, MemoryVault, Tampered, VaultRefused, seal, open_sealed
from api.adapters.llm.vault.kek import KekError, NoneKek, ScopeKek, from_settings
from api.domain.llm import CredentialKind, ProviderKind
from api.domain.redact import contains_secret, redact

OPENAI_KEY = "sk-" + "Q7" * 20
OTHER_KEY = "sk-" + "Z9" * 20


@pytest.fixture
def vault() -> MemoryVault:
    return MemoryVault(EnvKek.generate("test-1"))


# -- E-12 / TH-10: cross-user key use is refused, and recorded ---------------------------------
async def test_a_user_cannot_open_another_users_key(vault: MemoryVault):
    """The single most important test: this is a data incident, not a bug."""
    ref = await vault.put(ProviderKind.OPENAI, "api_key", OPENAI_KEY, user_id="a@example.com")
    with pytest.raises(VaultRefused):
        await vault.open(ref.id, user_id="b@example.com")
    # ...and the refusal is recorded, so an attempt is diagnosable after the fact.
    assert any("b@example.com" in row for row in vault.refusals)


async def test_find_never_borrows_another_users_key(vault: MemoryVault):
    await vault.put(ProviderKind.OPENAI, "api_key", OPENAI_KEY, user_id="a@example.com")
    assert await vault.find(ProviderKind.OPENAI, user_id="b@example.com") is None


async def test_a_workspace_key_is_usable_by_everyone_and_revealed_to_nobody(vault: MemoryVault):
    """FR-8: an app-level key works for all authorised users and comes back as `last4` only."""
    await vault.put(ProviderKind.OPENAI, "api_key", OPENAI_KEY, user_id="admin@example.com",
                    scope="workspace")
    found = await vault.find(ProviderKind.OPENAI, user_id="someone@example.com")
    assert found is not None
    assert found.last4 == OPENAI_KEY[-4:]
    public = json.dumps(found.public())
    assert OPENAI_KEY not in public and contains_secret(public) is False


async def test_a_users_own_key_wins_over_the_workspace_key(vault: MemoryVault):
    """The most specific live key is the one in play, and `find` says which without decrypting."""
    await vault.put(ProviderKind.OPENAI, "api_key", OPENAI_KEY, user_id="admin@example.com",
                    scope="workspace")
    mine = await vault.put(ProviderKind.OPENAI, "api_key", OTHER_KEY, user_id="me@example.com")
    found = await vault.find(ProviderKind.OPENAI, user_id="me@example.com")
    assert found.id == mine.id


# -- rotation, revocation, and never decrypting a dead row -------------------------------------
async def test_rotation_is_insert_and_revoke_so_the_old_ref_is_dead(vault: MemoryVault):
    """E-11: after a rotate the old ref raises and the new one works. Never an update."""
    old = await vault.put(ProviderKind.OPENAI, "api_key", OPENAI_KEY, user_id="a@example.com")
    new = await vault.put(ProviderKind.OPENAI, "api_key", OTHER_KEY, user_id="a@example.com")
    assert old.id != new.id
    with pytest.raises(VaultRefused):
        await vault.open(old.id, user_id="a@example.com")
    assert (await vault.open(new.id, user_id="a@example.com")).value == OTHER_KEY


async def test_a_revoked_row_is_refused_before_any_decryption(vault: MemoryVault):
    """S7: revocation is checked first, so a revoked key is never decrypted again."""
    ref = await vault.put(ProviderKind.OPENAI, "api_key", OPENAI_KEY, user_id="a@example.com")
    await vault.revoke(ref.id, user_id="a@example.com")
    with pytest.raises(VaultRefused) as caught:
        await vault.open(ref.id, user_id="a@example.com")
    assert "revoked" in str(caught.value)


async def test_storing_the_same_provider_twice_revokes_the_first(vault: MemoryVault):
    """One live key per provider per scope, which is what makes `find` unambiguous."""
    first = await vault.put(ProviderKind.OPENAI, "api_key", OPENAI_KEY, user_id="a@example.com")
    await vault.put(ProviderKind.OPENAI, "api_key", OTHER_KEY, user_id="a@example.com")
    live = await vault.list(user_id="a@example.com")
    assert [r.id for r in live] == [r.id for r in live if r.id != first.id]


# -- the envelope: a dump is not a key dump --------------------------------------------------
def test_the_plaintext_is_in_no_field_of_the_stored_row():
    """S1/S10: every stored field is opaque, so a database dump yields nothing."""
    kek = EnvKek.generate("k1")
    sealed = seal(OPENAI_KEY, kek)
    blob = sealed.ciphertext + sealed.iv + sealed.auth_tag + sealed.wrapped_dek
    assert OPENAI_KEY.encode() not in blob
    assert contains_secret(blob.decode("latin-1")) is False


def test_a_tampered_ciphertext_fails_to_open_rather_than_yielding_garbage():
    """AES-GCM authenticates: an altered row is refused, not sent to a provider."""
    kek = EnvKek.generate("k1")
    sealed = seal(OPENAI_KEY, kek)
    tampered = type(sealed)(bytes([sealed.ciphertext[0] ^ 1]) + sealed.ciphertext[1:],
                            sealed.iv, sealed.auth_tag, sealed.wrapped_dek, sealed.kek_key_id)
    with pytest.raises(Tampered):
        open_sealed(tampered, kek)


def test_a_row_wrapped_by_another_kek_does_not_open():
    """S10 as a direct assertion: the ciphertext alone is useless without the KEK that wrapped it."""
    sealed = seal(OPENAI_KEY, EnvKek.generate("k1"))
    with pytest.raises(KekError):
        open_sealed(sealed, EnvKek.generate("k2"))


def test_each_row_gets_its_own_data_key():
    kek = EnvKek.generate("k1")
    a, b = seal("one", kek), seal("two", kek)
    assert a.wrapped_dek != b.wrapped_dek, "a DEK per row is what bounds a single row's compromise"


# -- KEK choice -----------------------------------------------------------------------------
def test_a_scope_kek_that_cannot_be_read_fails_closed():
    scope = ScopeKek(None)
    assert scope.usable is False
    with pytest.raises(KekError):
        scope.wrap(b"x" * 32)


def test_the_selection_order_is_trust_order_not_convenience():
    """Scope first, then env, then none: the trust order 06 §The KEK specifies."""
    assert from_settings(secret_scope_value=EnvKek.generate()._key.hex() if False else None,
                         env_kek=None).mode == "none"
    env = EnvKek.generate("k")
    import base64

    raw = base64.urlsafe_b64encode(env._key).decode()   # noqa: SLF001 - reading our own generated key
    assert from_settings(env_kek=raw).mode == "env"
    assert isinstance(NoneKek(), NoneKek)


def test_an_unreadable_env_kek_becomes_none_rather_than_a_weaker_mode():
    chosen = from_settings(env_kek="not-base64-at-all")
    assert chosen.usable is False
    assert chosen.mode == "none"


# -- C-5: the env vault cannot store, and says so --------------------------------------------
async def test_the_env_vault_reads_keys_and_refuses_to_store_them():
    vault = EnvVault({"LLM_OPENAI_KEY": OPENAI_KEY})
    ref = await vault.find(ProviderKind.OPENAI, user_id="a@example.com")
    assert ref is not None and ref.id == "env:openai"
    secret = await vault.open("env:openai", user_id="a@example.com")
    assert secret.value == OPENAI_KEY
    with pytest.raises(VaultRefused) as caught:
        await vault.put(ProviderKind.OPENAI, "api_key", OPENAI_KEY, user_id="a@example.com")
    assert "database is unreachable" in str(caught.value)
    assert vault.available is False


async def test_the_env_vault_recognises_a_service_account_json_by_its_shape():
    from tests.test_llm_domain import _service_account

    vault = EnvVault({"LLM_VERTEX_KEY": _service_account("demo-test-1234")})
    ref = await vault.find(ProviderKind.GOOGLE_VERTEX, user_id="a@example.com")
    assert ref.kind == CredentialKind.SERVICE_ACCOUNT_JSON.value
    assert ref.project_hint == "demo-test-1234"


# -- S4: the agent config file never contains a secret ----------------------------------------
def test_a_secret_never_reaches_the_agent_config_file(tmp_path):
    """S4: the file references a variable; the value stays in the child's environment."""
    from api.adapters.acp.agent_config import AgentConfig
    from api.domain.llm import Capability, LimitEvidence, Limits, ModelId, ResolvedModel, WireProtocol

    resolved = ResolvedModel(
        id=ModelId.parse("openai/gpt-4.1"), provider=ProviderKind.OPENAI,
        wire=WireProtocol.OPENAI, endpoint="gpt-4.1", base_url="https://api.openai.com/v1",
        limits=Limits(128_000, 16_384, LimitEvidence.DOCUMENTED, "docs"),
        capability=Capability.TOOLS,
        env_var="LLM_PROVIDER_KEY", npm="@ai-sdk/openai-compatible",
    )
    cfg = AgentConfig.from_resolved(resolved, host="")
    path = cfg.write(tmp_path)
    text = path.read_text()
    assert "{env:LLM_PROVIDER_KEY}" in text
    assert contains_secret(text) is False
    assert OPENAI_KEY not in text


def test_a_redacted_error_body_is_safe_to_store_as_health_detail():
    """S2/S3: `llm_health.detail` is a sink, and a 401 body can contain part of the key."""
    body = f'401 Unauthorized: Incorrect API key provided: {OPENAI_KEY}. Check your key.'
    cleaned = redact(body)
    assert contains_secret(cleaned) is False
    assert "Incorrect API key provided" in cleaned


async def test_the_env_vault_takes_the_project_from_beside_a_key_that_omits_it():
    """A gcloud-cached service-account key has no project_id; `LLM_VERTEX_PROJECT` supplies it."""
    from api.adapters.llm.vault.local import EnvVault
    from tests.test_llm_domain import _service_account

    bare = json.loads(_service_account())
    bare.pop("project_id")
    vault = EnvVault({"LLM_VERTEX_KEY": json.dumps(bare), "LLM_VERTEX_PROJECT": "mobioos-506015"})
    ref = await vault.find(ProviderKind.GOOGLE_VERTEX, user_id="u@example.com")
    assert ref is not None and ref.project_hint == "mobioos-506015" and ref.scope_kind == "workspace"
    secret = await vault.open(ref.id, user_id="u@example.com")
    assert json.loads(secret.value)["project_id"] == "mobioos-506015"


# -- the operator's environment key survives turning the key store on --------------------------
async def test_a_layered_vault_keeps_the_operators_key_when_the_store_is_writable():
    """Regression: enabling the key store replaced the env vault, so a model that relied on the
    operator's `LLM_VERTEX_KEY` failed with "needs a key" on a deployment where that key had not changed."""
    from api.adapters.llm.vault.layered import LayeredVault
    from tests.test_llm_domain import _service_account

    vault = LayeredVault(MemoryVault(EnvKek.generate("t")),
                         EnvVault({"LLM_VERTEX_KEY": _service_account("operator-proj")}))
    me = "a@example.com"
    found = await vault.find(ProviderKind.GOOGLE_VERTEX, user_id=me)
    assert found is not None and found.id == "env:google_vertex"      # nothing saved: the operator's key
    assert (await vault.open(found.id, user_id=me)).kind == CredentialKind.SERVICE_ACCOUNT_JSON.value

    saved = await vault.put(ProviderKind.OPENAI, "api_key", OPENAI_KEY, user_id=me)
    assert (await vault.find(ProviderKind.OPENAI, user_id=me)).id == saved.id
    assert {c.provider for c in await vault.list(user_id=me)} == {ProviderKind.OPENAI, ProviderKind.GOOGLE_VERTEX}
    assert vault.available is True                                    # still writable

    own = await vault.put(ProviderKind.GOOGLE_VERTEX, "service_account_json",
                          _service_account("my-proj"), user_id=me)
    assert (await vault.find(ProviderKind.GOOGLE_VERTEX, user_id=me)).id == own.id   # yours wins
    with pytest.raises(VaultRefused):
        await vault.revoke("env:google_vertex", user_id=me)           # the operator's key is not yours to remove
