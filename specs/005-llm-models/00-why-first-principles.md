# 00 · Why, from first principles

[Index](README.md) · next: [01 Current state](01-current-state.md)

This document derives the design from what a model *is* to this product, rather than from the shape
of the code that picks one. Where a claim has a source, it is cited. Labels are explained in the
[index](README.md#provenance-of-the-claims-in-this-spec).

---

## The five whys

**1. Why does the app need more models?**
Because the model is the largest single lever on whether a task succeeds, and the app cannot use the
best model it has measured. Same tools, same rules, same tasks: **39%** with the gateway model,
**86%** with Gemini 3.8 Flash, and **71% → 99%** across setups
([README, findings #2 and #3](../../README.md), generated from `exams/results/`). A product whose
quality swings by 47 points depending on a dropdown it does not fully control has a feature gap, not
a configuration detail.

**2. Why can it not use them today?**
Because the catalogue is a Python list ([`api/config.py:32-41`](../../apps/coding-agent/api/config.py))
and the provider block is singular
([`agent_config.py:37-66`](../../apps/coding-agent/api/adapters/acp/agent_config.py)). Five ids are
offered; anything else is a code change and a deploy. And the gateway roster is gated: `system.ai.claude-*`
and `system.ai.gemini-*` returned `MODEL is not enabled` (`INVALID_STATE`) until an account admin
enables the Unity Gateway beta ([original spec §3.2](../../docs/genie-code-replacement-spec.md)) —
so the *best measured* model was, for a while, only reachable outside the gateway, through Vertex AI
with a Google credential ([`docs/02-setup-in-the-databricks-shell.md` §Step 4](../../docs/02-setup-in-the-databricks-shell.md)).

**3. Why is that a product problem and not an admin problem?**
Because the workaround exists and is documented — a local signature shim
([`experiments/gemini_sig_shim.py`](../../experiments/gemini_sig_shim.py)) in front of Vertex — and
it is *outside* the product: a hand-written proxy, a one-hour access token in a file, and a shell
script. Everything the fence exists to prevent, the workaround does by hand. When the only way to
use the best model is to leave the fenced application, the fence has already lost.

**4. Why not just add Gemini to the allow-list?**
Because three independent things break, and each one breaks *silently*:
(a) the config schema has one provider slot and one credential variable
([`agent_config.py:55-56`](../../apps/coding-agent/api/adapters/acp/agent_config.py));
(b) the agent receives exactly one secret
([`orchestrator.py:227-229`](../../apps/coding-agent/api/services/orchestrator.py));
(c) Gemini 3.x attaches an opaque `thought_signature` to every tool call that **must** be echoed
back, and generic OpenAI-compatible adapters drop it — measured, with the upstream error captured
verbatim in [`docs/e2e/07_gemini_thought_signature_failure.txt`](../../docs/e2e/07_gemini_thought_signature_failure.txt):

```
Function call is missing a thought_signature in functionCall parts.
This is required for tools to work correctly ...
function call `default_api:write`, position 2
```

That is not a config entry. It is a wire-protocol difference, and it is the reason
[04 · Providers](04-providers.md) exists rather than a footnote.

**5. Why is a registry the answer rather than a longer list?**
Because the list is not the problem; **the assumptions baked around the list are**. The list assumes
one provider, one credential, one id dialect, one set of limits known at build time, and a developer
present at deploy time. A registry replaces all five assumptions with data and one resolution step,
which is the smallest change that makes the fourth, fifth and hundredth model cost the same as the
second.

---

## First principles

Strip the product to what cannot be argued with. These are the premises the design must satisfy; the
document that satisfies each is named.

### P1 · A model is identified by three things, never by its name

A model call needs: **where** (base URL and wire protocol), **what** (the model identifier that
endpoint expects), and **who** (a credential). A single string like
`databricks/databricks-llama-4-maverick` carries none of them unambiguously. Today the app recovers
`where` and `what` by stripping a prefix and replacing dots with dashes
([`agent_config.py:180-189`](../../apps/coding-agent/api/adapters/acp/agent_config.py)) — string
surgery standing in for a lookup, which is why an unknown id produces a plausible wrong endpoint
instead of an error.

> **Law 1.** A model id resolves through a table, not through string manipulation. Any id that the
> table cannot resolve is an error at the boundary, before a process starts.
> Satisfied by [03 §The resolution pipeline](03-architecture.md#the-resolution-pipeline) and
> [05 §Tables](05-data-model-lakebase.md#tables).

### P2 · The wire protocols genuinely differ, so the provider is an adapter

Four protocols are in play, and they are not interchangeable
([verified] for the first two, [documented] for the others):

| Protocol | Endpoint shape | Credential | Known trap |
|---|---|---|---|
| Databricks serving | `{host}/serving-endpoints` | workspace token | per-endpoint output caps (`max_tokens 24000 cannot exceed 8192`) |
| OpenAI-compatible | `{base}/v1` | API key | — |
| Anthropic messages | `{base}/v1` | `x-api-key` + version header | tool-streaming flag |
| Google Vertex / Gemini | `{vertex}/projects/{p}/locations/{l}/endpoints/openapi` | OAuth token **or** service-account JSON | `thought_signature` round-trip |

The Gemini trap is the proof by example: a protocol difference that no amount of correct
configuration can paper over ([`docs/e2e/07_gemini_thought_signature_failure.txt`](../../docs/e2e/07_gemini_thought_signature_failure.txt)).

> **Law 2.** Provider-specific behaviour lives in one adapter per protocol, behind one interface, and
> the domain never branches on a provider name.
> Satisfied by [04](04-providers.md) and [03 §Ports and adapters](03-architecture.md#ports-and-adapters).

### P3 · Limits are properties of the endpoint, and being wrong breaks the model

Measured, in three different models
([original spec §3.2](../../docs/genie-code-replacement-spec.md)):

```
max_new_tokens 32000 cannot be greater than max_output_tokens 25000   (gpt-oss-120b)
max_tokens (24000) cannot exceed 10000                                (qwen3-next-80b)
max_tokens (24000) cannot exceed 8192                                 (llama-4-maverick)
```

A wrong cap is not a degraded experience; the model is unusable and the failure arrives as a
provider 400 *after* the user has waited. The app already encodes this as a dict
([`agent_config.py:84-91`](../../apps/coding-agent/api/adapters/acp/agent_config.py)) with a test that
guards it ([`tests/test_genie_features.py:512-519`](../../apps/coding-agent/tests/test_genie_features.py)).
That dict is correct and must not be deleted — it must become **data with provenance**, and the guard
must become a property of the resolver rather than of one test.

> **Law 3.** The request the app emits never exceeds the limits it believes the endpoint has, and it
> believes a measured number or an explicitly-marked guess.
> Satisfied by [05 §Limit evidence](05-data-model-lakebase.md#limit-evidence) and E-3 in
> [10](10-edge-cases-testing.md#model-identity-and-limits).

### P4 · A credential is a capability, and capabilities are the security boundary

The app's own security model is "least privilege by identity, not by prompt"
([001 09](../001-databricks-coding-agents/09-security-security.md)). A user-supplied provider key
is the strongest violation of that model available: it is a long-lived, unscoped secret that grants
spend and data egress outside Unity Catalog, where no grant, no audit table and no ACL applies.

The existing invariant is explicit: the token is read from the agent's environment
"never written into this file: a config on disk is a secret on disk"
([`agent_config.py:55-56`](../../apps/coding-agent/api/adapters/acp/agent_config.py)), and the tool
server's token arrives through a `0700` file
([`orchestrator.py:250-262`](../../apps/coding-agent/api/services/orchestrator.py)).

> **Law 4.** A credential is decrypted only in the process that uses it, only for the duration of a
> turn, and is never persisted in plaintext, returned by an API, or logged. One injection
> mechanism serves every provider.
> Satisfied by [06](06-security-credentials.md).

### P5 · A model choice must be pinned and provable

001 D-15 already decided this: "Model choice visible per message — makes routing legible and
debuggable" ([001 14](../001-databricks-coding-agents/14-decisions-risks.md)). Today the session
stores a `model` field ([`api/domain/session.py:63`](../../apps/coding-agent/api/domain/session.py))
and the turn event carries it
([`orchestrator.py:332-333`](../../apps/coding-agent/api/services/orchestrator.py)), but the field is
*rewritten* by a switch while a session is live
([`orchestrator.py:271-282`](../../apps/coding-agent/api/services/orchestrator.py)), so a transcript
can show one model for turns that ran on another. That is a provenance bug, and provenance is the
product.

> **Law 5.** A turn records the model id, the provider, the resolved endpoint and the wire protocol it
> actually used, as immutable facts.
> Satisfied by [05 §Immutability](05-data-model-lakebase.md#llmturnmodel-the-audit-record) and E-6 in
> [10](10-edge-cases-testing.md#switching-and-provenance).

### P6 · Failure is the common case, and it must speak provider

ACP has no "the model call failed" signal; the runtime already has a 180-second idle guard and a
stderr tail heuristic for exactly this reason
([`api/adapters/acp/runtime.py:19-20`](../../apps/coding-agent/api/adapters/acp/runtime.py),
[`:136-166`](../../apps/coding-agent/api/adapters/acp/runtime.py)), and the probe recorded a
model-switch failure surfacing as `-32603 Internal error: getaddrinfo ENOTFOUND https`
([`docs/e2e/20_acp_config_probe.txt`](../../docs/e2e/20_acp_config_probe.txt) §C) — a DNS error,
because the provider could not be reached, reported as an internal error.

> **Law 6.** Every model call is classified: reachable or not, authorised or not, capped or not. The
> classification is produced *before* the turn where possible and *named* during it where not.
> Satisfied by [04 §Health](04-providers.md#health-and-classification) and E-9 in
> [10](10-edge-cases-testing.md#discovery-and-health).

---

## The gap this spec must close

| Premise | Today | After |
|---|---|---|
| P1 id → (where, what, who) | string surgery, one convention | table lookup, explicit alias map |
| P2 protocols | one (`openai-compatible` against serving endpoints) | four, behind one adapter port |
| P3 limits | a dict in source, guarded by one test | data with provenance, clamped in the resolver, guarded by a property test |
| P4 credentials | one workspace token | vault with envelope encryption, per-user and per-app |
| P5 pinning | mutable session field | immutable per-turn record |
| P6 failure | idle timeout + stderr heuristic | classification + health probe + provider's own words |

---

## What this deliberately does not claim

1. **"Best model wins."** The measurements say the model dominates *with these tools and rules*
   ([README findings](../../README.md)); they do not say a stronger model needs no engineering —
   finding #3 says the opposite in the other direction.
2. **"External models are as safe as gateway models."** They are not: egress and spend leave the
   governance boundary ([06 §What changes in the threat model](06-security-credentials.md#what-changes-in-the-threat-model)).
3. **"Every gateway model will work."** Some return `MODEL is not enabled`; the registry records
   that as a state, not a filter that hides it ([02 R-9](02-requirements.md#requirements-that-constrain-the-design)).
4. **"The thought-signature problem is solved by configuration."** It is solved by an adapter that
   round-trips the field ([04 §Gemini](04-providers.md#gemini-on-vertex-ai)) or by a shim; the spec
   ships the former and keeps the latter as the documented fallback.

---

## The four axioms that follow

Short forms used throughout, so later documents can cite one line instead of a page.

| Axiom | Statement | Consequence if violated |
|---|---|---|
| **A1** | A model id resolves through data, never through string manipulation | a typo becomes a wrong endpoint, not an error |
| **A2** | Provider differences live in an adapter; the domain never branches on a vendor | every new vendor edits the core |
| **A3** | A limit is a measurement with provenance, or it is explicitly unknown | the model cannot be used at all |
| **A4** | A credential is decrypted per use and never stored or returned in the clear | the app becomes a key exfiltration path |
| **A5** | A turn's model is an immutable fact, not a current setting | the transcript lies |

Next: [01 · Current state](01-current-state.md), which measures the distance between A1–A5 and the code.
