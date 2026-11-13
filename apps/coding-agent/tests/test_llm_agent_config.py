"""The golden file, and the CI gates that are code rather than convention.

The golden file is the most important assertion in this spec: everything measured in this repository
— the 39 %→86 % model comparison, the 19 %→94 % working-agreement result — ran on **this exact
`opencode.json`**. If it changes by one byte, those numbers stop being comparable to anything here.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1]
API = APP / "api"

#: The exact file the shipped app writes for a Databricks model, captured before this spec changed the
#: code. `tests/fixtures/opencode.databricks.golden.json` is the byte-for-byte expectation.
GOLDEN = Path(__file__).resolve().parent / "fixtures" / "opencode.agent014.golden.json"


def test_the_databricks_agent_config_is_byte_identical_to_the_shipped_one():
    """P4's acceptance: if this fails, stop and diff. The config must not change."""
    from api.adapters.acp.agent_config import config_for

    cfg = config_for("databricks/databricks-llama-4-maverick", "h.example.com")
    rendered = json.dumps(cfg.as_opencode_json(), indent=2)
    assert rendered == GOLDEN.read_text().rstrip("\n"), (
        "the Databricks agent config changed; the measurements in this repository are no longer "
        "comparable. Diff against tests/fixtures/opencode.databricks.golden.json and revert unless "
        "the change is intentional.")


def test_the_golden_config_carries_the_token_variable_not_a_token():
    """S4, asserted on the golden bytes as well as on behaviour: the invariant must not drift."""
    text = GOLDEN.read_text()
    assert "{env:DATABRICKS_TOKEN}" in text
    assert not re.search(r"dapi[a-f0-9]{32}", text)


def test_the_working_agreement_is_unchanged_in_substance():
    """`AGENTS.md` is what took the exam score from 19 % to 94 %; it must still be written."""
    from api.adapters.acp.agent_config import WORKING_AGREEMENT

    for phrase in ("Act, do not speculate", "Describe before you write", "Evidence",
                   "Assumptions and unverified", "Fully qualify every object"):
        assert phrase in WORKING_AGREEMENT, phrase


# -- C-2: the domain is vendor-free ---------------------------------------------------------
VENDOR_BRANCH = re.compile(r"==\s*['\"](databricks|openai|anthropic|google_vertex)['\"]")


def test_no_vendor_comparison_in_the_domain_or_the_services():
    """A2: a new provider must not edit the core. A string comparison is how it would start."""
    offenders = []
    for directory in ("domain", "services"):
        for path in (API / directory).rglob("*.py"):
            for number, line in enumerate(path.read_text().splitlines(), start=1):
                if VENDOR_BRANCH.search(line):
                    offenders.append(f"{path.relative_to(APP)}:{number}: {line.strip()}")
    assert not offenders, f"a vendor branch reached the core: {offenders}"


def test_the_only_vendor_names_left_are_provider_kind_members_and_adapter_files():
    """C-2's grep, precisely: a vendor name **as a string literal** outside an adapter is the bug.

    An enum member (`ProviderKind.OPENAI`) is how the code refers to a provider deliberately — it is
    exhaustive and it fails at import if a provider is added. What must not appear is the raw string,
    because that is what a branch on a vendor looks like and what silently fails to match a typo.
    """
    pattern = re.compile(r"""['"](databricks|openai|anthropic|google_vertex|vertex)['"]""")
    #: Files that must name a provider: the enum, the seed data, the adapters, and copy shown to a
    #: person. Everything else is a regression.
    allowed_prefixes = ("api/adapters/", "api/domain/llm/")
    allowed = {"api/adapters/acp/agent_config.py", "api/services/model_resolver.py",
               "api/composition/model_registry.py", "api/services/credential_service.py",
               # SQL grammar selection is a dialect, not a model-provider branch.
               "api/domain/sqlpolicy.py",
               # A Databricks adapter: it shells out to the `databricks` CLI to refresh a local
               # development token. Naming the vendor is the point of the file, and it is the only
               # place the name may appear for this reason (see `api/adapters/databricks/devtoken.py`).
               "api/adapters/databricks/devtoken.py"}
    offenders = []
    for path in API.rglob("*.py"):
        rel = str(path.relative_to(APP))
        if rel.startswith(allowed_prefixes) or rel in allowed:
            continue
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if pattern.search(line):
                offenders.append(f"{rel}:{number}: {line.strip()[:90]}")
    assert not offenders, f"a vendor string reached the core: {offenders}"


# -- C-3: one resolver ----------------------------------------------------------------------
def test_config_for_is_defined_once_and_known_endpoints_is_gone():
    """C-3's grep test, as a test: one definition, and no string surgery surviving beside it."""
    definitions = 0
    for path in API.rglob("*.py"):
        definitions += len(re.findall(r"^\s*def config_for\(", path.read_text(), re.M))
    assert definitions == 1, f"config_for has {definitions} definitions"

    offenders = [str(p.relative_to(APP)) for p in API.rglob("*.py")
                 if "KNOWN_ENDPOINTS" in p.read_text()]
    assert not offenders, f"the old endpoint table survives in {offenders}"


def test_the_limits_guard_iterates_the_registry_not_a_python_list():
    """C-4: the guard is a property of the resolver over the catalogue, not of `Settings`."""
    from api.domain.llm import LimitEvidence
    from api.composition.model_registry import _seed

    offered = list(_seed().models)
    assert offered, "the seed file is empty"
    for spec in offered:
        assert spec.endpoint, f"{spec.id.value} resolves to no endpoint"
        assert spec.wire is not None, f"{spec.id.value} has no wire protocol"
        assert spec.limits.output <= spec.limits.context, spec.id.value
        # Every limit is proven or explicitly flagged; a silent guess is the bug A3 forbids.
        assert spec.limits.evidence in tuple(LimitEvidence), spec.id.value
        if spec.limits.evidence is LimitEvidence.DEFAULT:
            assert spec.limits.output <= 4_000, f"{spec.id.value} guesses a large cap"


def test_every_seeded_credential_kind_matches_its_provider():
    """A model that needs a key must say which kind, or the settings form cannot ask for it."""
    from api.domain.llm import CredentialKind
    from api.composition.model_registry import _seed

    for spec in _seed().models:
        if spec.id.provider.value == "databricks":
            assert spec.credential_kind is CredentialKind.NONE, spec.id.value
        else:
            assert spec.credential_kind is not CredentialKind.NONE, spec.id.value


def test_the_resolver_is_the_only_place_a_url_is_built():
    """Pure config serialization and URL normalization are values, never network adapters.

    Spec 014 moves them into the domain so lifecycle services do not import the ACP adapter.
    Other domain modules still may not assemble provider URLs.
    """
    pure_values={API / 'domain/urls.py', API / 'domain/llm/agent_config.py'}
    for value in pure_values:
        assert 'httpx' not in value.read_text()
        assert 'from ..adapters' not in value.read_text()
    offenders = []
    for path in (API / "domain").rglob("*.py"):
        text = path.read_text()
        if "https://" in text and path not in pure_values:
            offenders.append(str(path.relative_to(APP)))
    assert not offenders, f"a URL reached the domain: {offenders}"


# -- the seed file is data, and it validates ------------------------------------------------
def test_the_seed_file_parses_into_valid_value_objects():
    from api.adapters.llm.store.seed import load

    seed = load()
    assert len(seed.providers) == 4, "the four provider kinds FR-3 names"
    assert len(seed.models) >= 10
    assert seed.default_model == "google_vertex/google/gemini-3.8-flash"


def test_the_five_measured_caps_are_the_numbers_this_repository_earned():
    """A3: these five came from rejections in this workspace. If one is edited, it needs new evidence."""
    from api.adapters.llm.store.seed import load

    measured = {m.endpoint: m.limits.output for m in load().models
                if m.limits.evidence.value == "measured"}
    assert measured == {
        "databricks-llama-4-maverick": 8_000,
        "databricks-gpt-oss-120b": 24_000,
        "databricks-gpt-oss-20b": 24_000,
        "databricks-qwen3-next-80b-a3b-instruct": 10_000,
        "databricks-meta-llama-3-3-70b-instruct": 8_000,
    }


def test_the_seed_grants_nothing_because_authorisation_is_not_a_build_artefact():
    """05: grants come only from the database. A seed file that could grant would be a repository ACL."""
    from api.adapters.llm.store.seed import load

    text = (APP / "seed" / "llm_models.yaml").read_text()
    # No key, and no grant row: a `grant:` mapping or a `subject:` field would both be an ACL in a file.
    assert not re.search(r"^\s*(grants?|subject|subject_kind|allow)\s*:", text, re.M)
    assert all(spec.group == "" for spec in load().models), "a seed row claimed a grant-bearing group"


# -- Vertex native wire: validated against a real `opencode` run (Gemini 3.8 Flash) -----------
def _vertex_native():
    from api.domain.llm import Capability, ModelId, ProviderKind, ResolvedModel, WireProtocol
    from api.domain.llm.limits import Limits

    return ResolvedModel(
        id=ModelId.parse("google_vertex/google/gemini-3.8-flash"), provider=ProviderKind.GOOGLE_VERTEX,
        wire=WireProtocol.VERTEX_NATIVE, endpoint="gemini-3.8-flash", base_url="",
        limits=Limits(1_000_000, 30_000), capability=Capability.TOOLS,
        env_var="GOOGLE_APPLICATION_CREDENTIALS", npm="@ai-sdk/google-vertex",
        agent_id="google-vertex/gemini-3.8-flash")


def test_the_native_vertex_block_has_no_url_and_no_key_reference():
    """The built-in provider authenticates from the environment; a baseURL/apiKey here broke it."""
    from api.adapters.acp.agent_config import AgentConfig

    out = AgentConfig.from_resolved(_vertex_native()).as_opencode_json()
    assert out["model"] == "google-vertex/gemini-3.8-flash"
    block = out["provider"]["google-vertex"]
    assert set(block) == {"name", "models"}
    assert block["models"]["gemini-3.8-flash"]["limit"] == {"context": 1_000_000, "output": 30_000}
    assert "baseURL" not in json.dumps(out) and "apiKey" not in json.dumps(out)


def test_the_file_and_the_set_model_id_name_the_same_block():
    from api.adapters.acp.agent_config import AgentConfig

    resolved = _vertex_native()
    assert AgentConfig.from_resolved(resolved).model_ref() == resolved.agent_id
