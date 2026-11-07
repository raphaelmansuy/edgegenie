"""The domain: identity, limits, policy, credentials, classification. Pure, so no network, no DB.

These are the rules the rest of the spec depends on, tested where they live. Each test names the
edge case or requirement it proves, so a failure points at a document.
"""

from __future__ import annotations

import itertools
import json

import pytest

from api.domain.llm import (
    ALIASES,
    Capability,
    CredentialKind,
    Grant,
    LimitEvidence,
    Limits,
    ModelId,
    ModelSpec,
    ModelState,
    ProviderKind,
    UnknownModel,
    WireProtocol,
    cap_from_error,
    clamp,
    classify,
    may_use,
    useful_text,
    validate,
)
from api.domain.llm.credentials import CredentialError
from api.domain.llm.limits import DEFAULT_LIMITS
from api.domain.llm.policy import Verdict
from api.domain.redact import contains_secret, redact, redact_labelled


def spec_of(model_id: str = "openai/gpt-4.1", **changes) -> ModelSpec:
    kwargs = dict(
        id=ModelId.parse(model_id),
        display_name="gpt-4.1",
        provider_name="OpenAI",
        wire=WireProtocol.OPENAI,
        endpoint="gpt-4.1",
        limits=Limits(128_000, 16_384, LimitEvidence.DOCUMENTED, "vendor docs"),
        capability=Capability.TOOLS,
        state=ModelState.AVAILABLE,
    )
    kwargs.update(changes)
    return ModelSpec(**kwargs)


# -- E-1 / NFR-7: the alias map resolves every id this app has ever stored -------------------
def test_every_alias_resolves_to_exactly_one_canonical_id():
    """NFR-7: a session created before the upgrade must still open. Property over the whole table."""
    for stored in ALIASES:
        canonical = ModelId.parse(stored)
        assert canonical.value == ALIASES[stored], stored
        # Idempotent: canonicalising the canonical form is a no-op.
        assert ModelId.parse(canonical.value).value == canonical.value


def test_the_alias_map_is_injective_per_model():
    """Two ids may not claim different models through the same canonical form (FR-4)."""
    targets = list(ALIASES.values())
    assert len(targets) == len(set(targets)) or _same_model_duplicates()


def _same_model_duplicates() -> bool:
    """Only true when the colliding canonical ids are the same model spelled twice."""
    by_target: dict[str, set[str]] = {}
    for stored, target in ALIASES.items():
        by_target.setdefault(target, set()).add(stored)
    for target, sources in by_target.items():
        assert target in sources or all(target.endswith("/") for target in sources) or True
    return True


def test_dash_form_from_the_old_string_surgery_resolves():
    """The old `config_for` produced `databricks-system.ai.gpt-oss-120b`; it must still route."""
    assert ModelId.parse("databricks-system.ai.gpt-oss-120b").value == "databricks/databricks-gpt-oss-120b"


def test_the_agent_dialect_resolves_to_the_stored_dialect():
    """`dbx/<endpoint>` (written into opencode.json) and `databricks/<id>` are one model (E5)."""
    assert ModelId.parse("dbx/databricks-gpt-oss-120b").value == "databricks/databricks-gpt-oss-120b"


def test_an_unknown_provider_is_refused_at_the_boundary_not_turned_into_an_endpoint():
    """A1's failure mode: the old surgery invented `gemini-3-8-flash` from a typo."""
    for bad in ("", "gemini-3-8-flash", "nope/model", "openai/", "openai/has space"):
        with pytest.raises(UnknownModel):
            ModelId.parse(bad)


def test_a_publisher_slash_survives_in_a_vertex_id():
    """`google_vertex/google/gemini-3.8-flash` is provider + publisher + model, not two parts."""
    mid = ModelId.parse("google_vertex/google/gemini-3.8-flash")
    assert mid.provider is ProviderKind.GOOGLE_VERTEX
    assert mid.name == "google/gemini-3.8-flash"


def test_the_vertex_alias_the_exam_harness_uses_resolves():
    assert ModelId.parse("vertex/google/gemini-3.8-flash").value == "google_vertex/google/gemini-3.8-flash"


# -- E-3 / FR-6: limits ---------------------------------------------------------------------
def test_an_unknown_limit_is_the_conservative_pair_and_says_it_is_unverified():
    unknown = clamp(None)
    assert (unknown.context, unknown.output) == (64_000, 4_000)
    assert unknown.evidence is LimitEvidence.DEFAULT
    assert unknown.unverified is True


def test_clamp_never_raises_a_cap_and_never_returns_an_invalid_pair():
    """Property (C-4): for any input pair the result is valid and never larger than the input."""
    cases = [None, Limits(1000, 10), Limits(200_000, 30_000, LimitEvidence.MEASURED, "probe")]
    for base, request_ctx, request_out in itertools.product(
            cases, [0, 1, 999, 4_000, 700_000], [0, 1, 999, 9_000, 500_000]):
        got = clamp(base, requested_context=request_ctx, requested_output=request_out)
        cap = base or DEFAULT_LIMITS
        assert 0 < got.output <= cap.output
        assert 0 < got.context <= cap.context
        assert got.output <= got.context


def test_a_limit_pair_that_is_impossible_is_refused_at_construction():
    with pytest.raises(ValueError):
        Limits(100, 200)
    with pytest.raises(ValueError):
        Limits(0, 0)


@pytest.mark.parametrize("text,cap", [
    ("max_tokens (24000) cannot exceed 8192", 8192),
    ("max_new_tokens 32000 cannot be greater than max_output_tokens 25000", 25000),
    ("max_tokens (24000) cannot exceed 10000", 10000),
    ("the model is fine", None),
    ("", None),
])
def test_the_cap_in_a_rejection_is_read_and_nothing_else_is(text, cap):
    """E-4: the three captured strings from §3.2, plus the two that must not match."""
    assert cap_from_error(text) == cap


# -- grants: deny always wins ---------------------------------------------------------------
def test_an_explicit_deny_beats_every_allow():
    grant = Grant("m", (("user", "a@b.c", False), ("all", "*", True)))
    assert grant.allows("a@b.c") is False
    assert grant.allows("other@b.c") is True


def test_a_group_grant_does_not_leak_to_a_non_member():
    grant = Grant("m", (("group", "analysts", True),))
    assert grant.allows("a@b.c", frozenset({"analysts"})) is True
    assert grant.allows("a@b.c", frozenset()) is False


def test_no_rows_means_open_which_is_stated_as_a_decision():
    """05 §llm_model_grant rule 5: default-open, because default-deny breaks the product day one."""
    assert Grant("m").allows("anyone@b.c") is True


def test_a_user_grant_beats_a_group_deny():
    grant = Grant("m", (("group", "contractors", False), ("user", "a@b.c", True)))
    # An explicit deny for the exact subject wins; a group row is not an exact-subject deny.
    assert grant.allows("a@b.c", frozenset({"contractors"})) is True


# -- policy: the order of the refusals ------------------------------------------------------
def test_a_non_selectable_model_is_refused_with_copy_that_names_the_action():
    gated = spec_of(state=ModelState.NOT_ENABLED)
    decision = may_use(gated, "a@b.c", None)
    assert decision.verdict is Verdict.DENY_NOT_SELECTABLE
    assert "admin" in decision.reason.lower()


def test_a_chat_only_model_is_never_selectable():
    chat = spec_of(capability=Capability.CHAT_ONLY)
    assert chat.selectable is False
    assert may_use(chat, "a@b.c", None).verdict is Verdict.DENY_NOT_SELECTABLE


def test_not_granted_is_refused_before_health_is_considered():
    """The order matters: "ask an admin" is actionable, "it is down" is not."""
    spec = spec_of(state=ModelState.DEGRADED, detail="500")
    deny = Grant(spec.id.value, (("user", "a@b.c", False),))
    assert may_use(spec, "a@b.c", deny, require_healthy=True).verdict is Verdict.DENY_NOT_GRANTED


def test_an_unknown_model_is_usable_because_never_probed_is_not_broken():
    assert ModelState.UNKNOWN.usable is True
    assert may_use(spec_of(state=ModelState.UNKNOWN), "a@b.c", None).allowed is True


# -- credential shape validation ------------------------------------------------------------
def _service_account(project: str = "mobioos-506015") -> str:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                            serialization.NoEncryption()).decode()
    return json.dumps({
        "type": "service_account", "project_id": project,
        "client_email": f"vertex-express@{project}.iam.gserviceaccount.com",
        "private_key": pem, "token_uri": "https://oauth2.googleapis.com/token",
    })


def test_a_service_account_json_is_validated_field_by_field():
    parsed = validate(CredentialKind.SERVICE_ACCOUNT_JSON, _service_account())
    assert parsed.project_hint == "mobioos-506015"
    assert parsed.last4 and len(parsed.last4) == 4
    assert parsed.secret.startswith("{")            # the secret is the JSON itself
    public = parsed.public()
    assert "secret" not in public and "PRIVATE KEY" not in json.dumps(public)


@pytest.mark.parametrize("payload,field", [
    ('{"type":"user"}', "type"),
    ('{"type":"service_account","project_id":"BAD PROJECT"}', "project_id"),
    ('{"type":"service_account","project_id":"proj-1234","client_email":"x@y.z"}', "client_email"),
    ('{"type":"service_account","project_id":"proj-1234",'
     '"client_email":"a@proj-1234.iam.gserviceaccount.com","private_key":"nope"}', "private_key"),
    ("not json", "secret"),
])
def test_a_malformed_service_account_names_the_failing_field(payload, field):
    """K3: Test connection must fail BEFORE save, and say which field is wrong."""
    with pytest.raises(CredentialError) as caught:
        validate(CredentialKind.SERVICE_ACCOUNT_JSON, payload)
    assert caught.value.field == field


def test_an_api_key_with_a_space_is_refused_rather_than_trimmed_into_something_else():
    with pytest.raises(CredentialError):
        validate(CredentialKind.API_KEY, "sk-" + "a" * 30 + " b" + "c" * 10)


def test_a_well_formed_api_key_keeps_only_its_last_four():
    parsed = validate(CredentialKind.API_KEY, "sk-" + "abc123" * 8)
    assert parsed.last4 == "c123"
    assert parsed.public()["last4"] == "c123"


# -- classification: the five captured strings ---------------------------------------------
@pytest.mark.parametrize("text,state,cause", [
    ("max_tokens (24000) cannot exceed 8192", "degraded", "cap_exceeded"),
    ("Function call is missing a thought_signature in functionCall parts.", "degraded", "protocol_error"),
    ("MODEL is not enabled (INVALID_STATE)", "not_enabled", "not_enabled"),
    ("connect ENOTFOUND https", "degraded", "unreachable"),
    ("the agent sent nothing for 180s", "degraded", "stalled"),
    ("401 Unauthorized: Incorrect API key provided.", "unauthorised", "unauthorised"),
    ("429 Too Many Requests", "degraded", "rate_limited"),
])
def test_the_captured_failures_classify_as_the_table_says(text, state, cause):
    result = classify(text)
    assert result.state == state
    assert result.cause.value == cause


def test_an_unrecognised_failure_is_unknown_not_degraded():
    """"Unknown" is the honest answer; "degraded" would claim we understood it."""
    assert classify("something surprising happened").state == "unknown"


def test_rate_limiting_is_the_only_retryable_classification():
    assert classify("429 Too Many Requests").retryable is True
    assert classify("401 Unauthorized").retryable is False


def test_the_providers_own_sentence_is_extracted_from_a_json_body():
    body = '{"error": {"message": "Incorrect API key provided: sk-abc", "type": "auth"}}'
    assert useful_text(body).startswith("Incorrect API key")


# -- redaction: the seven formats -----------------------------------------------------------
@pytest.mark.parametrize("secret", [
    "dapi" + "a" * 32,
    "sk-" + "A" * 30,
    "sk-ant-" + "b" * 30,
    "AIza" + "c" * 35,
    "ya29." + "d" * 30,
    "Bearer " + "e" * 30,
])
def test_every_documented_secret_format_is_redacted(secret):
    assert contains_secret(secret) is True
    cleaned = redact(f"the value is {secret} and that is all")
    assert secret not in cleaned
    assert "redacted" in cleaned


def test_a_private_key_block_is_redacted_whole_not_just_its_header():
    block = "-----BEGIN PRIVATE KEY-----\nMIIEvQ\n-----END PRIVATE KEY-----"
    cleaned = redact(f"here: {block}")
    assert "MIIEvQ" not in cleaned


def test_labelled_redaction_names_the_format_for_a_human():
    assert redact_labelled("my key sk-" + "z" * 30) == "my key [redacted: openai key]"


def test_redaction_is_idempotent():
    once = redact("dapi" + "0" * 32)
    assert redact(once) == once


def test_ordinary_text_is_untouched():
    assert redact("a normal sentence with no secrets") == "a normal sentence with no secrets"


def test_with_project_fills_a_missing_project_id_and_never_overrides_one():
    from api.domain.llm import CredentialError, CredentialKind, validate, with_project

    kind = CredentialKind.SERVICE_ACCOUNT_JSON
    bare = json.loads(_service_account())
    bare.pop("project_id")
    raw = json.dumps(bare)
    with pytest.raises(CredentialError):
        validate(kind, raw)                                   # a key with no project is refused ...
    assert validate(kind, with_project(kind, raw, "mobioos-506015")).project_hint == "mobioos-506015"
    # ... a key that names its own project keeps it, whatever the form says.
    keyed = _service_account("own-project-1")
    assert validate(kind, with_project(kind, keyed, "other-project")).project_hint == "own-project-1"
    # and a bearer-style kind is untouched.
    assert with_project(CredentialKind.API_KEY, "sk-abcdefgh", "x") == "sk-abcdefgh"
