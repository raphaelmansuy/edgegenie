# 10 · Edge cases, tests, risks

[Index](README.md) · prev: [09 Implementation plan](09-implementation-plan.md) · next: [11 Decisions](11-decisions-risks.md)

Every case has **what happens**, **the mitigation**, and **the test that fails if the mitigation is
removed**. A case without a test is a wish; a mitigation without a failure mode is decoration.

Groups: **E-1…E-7 model identity and limits** · **E-8…E-13 credentials** · **E-14…E-17 storage and
scale** · **E-18…E-21 switching and provenance** · **E-22…E-25 discovery and health** ·
**E-26…E-29 the surface**.

---

## Model identity and limits

| # | Case | What happens | Mitigation | Test |
|---|---|---|---|---|
| **E-1** | A stored session id is one the registry does not know | `s.model` is a string from before the upgrade; the resolver raises | the alias map resolves every id in [04](04-providers.md#ids-and-the-alias-map); an unknown id yields `unknown_model` naming the id, not a crash | property test over a fixture list of every id the app has ever written; and NFR-7 as an integration test that loads a fixture session |
| **E-2** | Two models claim the same canonical id | the second upsert silently overwrites the first | the canonical id is the natural PK; a conflicting provider claim is refused at validation, and the two claims are shown side by side in the error | unit: upsert twice with different endpoints → second refused with both rows quoted |
| **E-3** | A model has no known limit | `DEFAULT_LIMITS` (64k / 4k) is applied, and the UI shows "unverified" | `evidence = default`, `source = 'assumed'`; the clamp is always applied | unit: a `ModelSpec` with `limits=None` resolves to `(64000, 4000)`, evidence `default`; the picker renders the unverified copy |
| **E-4** | An endpoint rejects the cap ("max_tokens 24000 cannot exceed 8192") | the turn fails after the user waited | the classifier parses the number and **lowers** the stored cap, `limit_source = "observed at <turn>"`; it never raises a cap from an error | unit: feed the three captured strings, assert the stored cap drops and the turn is classified `cap_exceeded`; assert a *higher* number in the error is ignored |
| **E-5** | A model supports chat but not tool calling | the agent loops without tools and produces an answer that claims work it did not do | `capability = chat_only` → not selectable, with the reason; a probe proves tool calling before a model is marked `tools` | unit: a provider stub that returns no tool calls → `chat_only`; integration: the picker never offers it |
| **E-6** | A model's context is smaller than the conversation | the provider truncates or errors mid-turn | the resolved context is passed into the agent config; the turn's token count is compared and a `context_pressure` warning is emitted before the hard limit | unit: a config with `context=8192` produces a warning at 80 %; integration: the agent config carries the number |
| **E-7** | The same model is served by two endpoints (Databricks and a compatible proxy) | two rows, two limits, two credentials — and a user cannot tell them apart | `display_name` must differ, or the UI appends the provider; the picker groups by provider so the distinction is structural | unit: two specs with the same model key → labels differ; component: both visible in their own groups |

---

## Credentials

| # | Case | What happens | Mitigation | Test |
|---|---|---|---|---|
| **E-8** | A key is pasted into a prompt | it would be stored in an event payload and possibly echoed | redaction at every sink; the turn continues with `[redacted: openai key]`; the event records that a redaction happened | E-13's scan, plus a test that posts a prompt containing `sk-…` and asserts the stored payload has no match |
| **E-9** | A key is wrong but well-formed | a 401 on the first turn | `Test connection` before save; after save, the classifier marks `unauthorised` and the row shows the provider's message | unit: classifier on the captured 401 body; e2e: a fake provider returning 401 → the model shows `unauthorised` and the copy matches [07](07-ux-ui-wireframes.md#copy-in-full) |
| **E-10** | A service-account JSON is valid but the project has no Vertex API enabled | the token mints, the call fails 403 with a project-specific message | `validate_secret` extracts and stores `project_hint`; the classifier surfaces the provider's text, which names the project | unit: a JSON with a valid key but a project the stub refuses → `unauthorised` with the project in the detail |
| **E-11** | A key is rotated at the provider | the app's stored key stops working | `Rotate` is insert + revoke, never update, so `last_used_at` history survives; the old row is never decrypted again | unit: after rotate, `open(old_ref)` raises and `open(new_ref)` succeeds |
| **E-12** | Two users store keys for the same provider | key confusion: A's session uses B's key | the vault scope is `(scope_kind, scope_id)`; resolution passes the session's user; a miss is `no_credential`, never a fallback | e2e: two users, two keys, a fake provider asserts each request's `Authorization` matches the session's user |
| **E-13** | A secret reaches a log, an event, an export or the browser | a leak that outlives the session | the seven patterns of [06](06-security-credentials.md#redaction-at-the-source), applied at the sink; a response-scan test over every `/api/llm/*` route; a repo scan | `tests/test_llm_secrets.py`: plant each pattern in a key, a provider error body and a prompt, then scan the app's captured output |

**E-12 is the one to write first.** It is the only case where a bug is a cross-tenant data incident rather
than a broken feature, and it is cheap to test with a fake provider.

---

## Storage and degradation

| # | Case | What happens | Mitigation | Test |
|---|---|---|---|---|
| **E-14** | No database | today's app works; a key store cannot | C-5: seed catalogue, Databricks models work, key actions disabled **with the reason**, `source: "seed"` in the response | integration: `LLM_DATABASE_URL` unset → `/api/models` 200, `source=seed`; `PUT /credentials` → 503 with the copy from [07](07-ux-ui-wireframes.md#copy-in-full) |
| **E-15** | The database dies after boot | every request raises | the store catches connection errors and falls back to the last catalogue in memory, `source: "degraded"`; a reconnect is retried with backoff and logged once | integration: kill the connection mid-test, assert `/api/models` still 200 and a Databricks session still starts |
| **E-16** | A migration runs twice | duplicate rows or a failed boot | every migration is idempotent (`IF NOT EXISTS`, `ON CONFLICT DO NOTHING`); `schema_version` is stamped | integration: apply twice, assert one schema version and unchanged row counts |
| **E-17** | The schema is ahead of the code (a rolled-back deploy) | the app writes against columns it does not know | boot refuses with a named error rather than degrading | integration: stamp a future version, assert the app does not start and the message names both versions |

---

## Switching and provenance

| # | Case | What happens | Mitigation | Test |
|---|---|---|---|---|
| **E-18** | The user switches model mid-turn | the running turn could report the new model | the turn's pin is written before the prompt and never updated; the switch applies to the next turn; the inspector names the turn it took effect on | integration: start a turn, switch, assert the first turn's pin is unchanged and the second's is new |
| **E-19** | A cross-provider switch while a tool is running | closing the child loses the tool result | the switch **drains** the current turn first (the runtime's `cancel` + 10 s shield, [`runtime.py:239-247`](../../apps/coding-agent/api/adapters/acp/runtime.py)) before closing | integration: a fake agent that emits a tool update after a delay, then a switch; assert the update is stored before the child is replaced |
| **E-20** | The ACP switch returns an error | the session claims a model it is not using | the switch is refused, the old model stays, the provider's words are surfaced; no pin is written | unit: `set_config_option` raises → `set_model` returns the old model and a typed error |
| **E-21** | The agent does not advertise the resolved model id | the switch would send an id the agent does not know | the resolver returns the **agent-side** id from the advertised list; if absent, the model is offered but the switch returns "restart required" | unit: advertised list without the id → the resolver's `agent_id` is empty and the switch takes the restart path |

---

## Discovery and health

| # | Case | What happens | Mitigation | Test |
|---|---|---|---|---|
| **E-22** | Discovery returns 403 | the catalogue would empty, revoking everything | `None` means **do not filter**, as today ([`serving.py:22-32`](../../apps/coding-agent/api/adapters/databricks/serving.py)); state stays, `source` degrades | unit: an HTTP layer raising `PermissionError` → catalogue unchanged |
| **E-23** | A model disappears from discovery | a session pinned to it cannot resume | `state = not_served`, the row is kept, the session shows "not served here" with a resume-with action | unit: discovery minus one model → row `not_served`, grants intact; component: the resume copy renders |
| **E-24** | A probe costs money | a health loop that burns tokens | probes run at most every `LLM_PROBE_SECONDS` (default 900), are skipped when a turn has succeeded recently, and use a one-token request | unit: a counter stub asserts ≤1 probe per interval per model |
| **E-25** | The provider returns 429 | the turn fails with no explanation | classified `rate_limited`; retried at most twice with backoff; the turn stays cancellable; the UI says "busy, retrying" | unit: a stub returning 429 twice then 200 → one success, two attempts, a `turn.retrying` event |

---

## The surface

| # | Case | What happens | Mitigation | Test |
|---|---|---|---|---|
| **E-26** | The catalogue has 200 models | an unusable list | grouping, search, collapse; virtualisation deferred with a measured threshold | component: 200 specs render, search narrows, first paint < 100 ms in the test harness |
| **E-27** | A model has no credential and no grant | the user cannot tell which is missing | two distinct states with two distinct copies (`no_credential` → add a key; `not_granted` → ask an admin) | unit: policy result → copy, exhaustively over the state enum |
| **E-28** | The popover opens at 200 % zoom | it overflows and traps the page | capped height with internal scroll; verified by `overflow-audit.mjs` | `npm run audit:overflow` at 200 % |
| **E-29** | A keyboard user opens the picker, types, and presses Enter on a disabled row | a silent no-op | disabled rows are not focusable-by-action; Enter on one announces the reason via `role="status"` | component: `aria-activedescendant` on a disabled row → Enter does not select and the status text is set |

---

## Secret hygiene

The checklist in [06](06-security-credentials.md#secret-hygiene-checklist-used-in-review-and-in-ci) is the
specification; this is how it is executed.

| Sink | How it is exercised | Assertion |
|---|---|---|
| API response | every `/api/llm/*` route called with a planted key | the response body contains neither the plaintext nor the ciphertext |
| event payload | a turn that stores a prompt containing a key | the stored payload matches the key regex set |
| log | a failing provider call that echoes the header | the captured log has no match |
| agent config file | any session start | the file contains `{env:` and no secret material |
| process env | start a session | `os.environ` of the app is unchanged |
| child env | `SessionSpec.env` | exactly one provider key, and only the selected one |
| database | a `SELECT *` of `llm_credential` | no column is plaintext; decryption without a KEK raises |
| export | a session export | no match, same regex set |

The regex set, generated from [06](06-security-credentials.md#redaction-at-the-source):

```python
SECRET_PATTERNS = [
    r"dapi[a-f0-9]{32}",
    r"sk-[A-Za-z0-9_\-]{20,}",
    r"sk-ant-[A-Za-z0-9_\-]{20,}",
    r"AIza[0-9A-Za-z_\-]{35}",
    r"ya29\.[0-9A-Za-z_\-]{20,}",
    r"-----BEGIN (RSA )?PRIVATE KEY-----",
    r"Bearer [A-Za-z0-9._\-]{20,}",
]
```

---

## Backward compatibility

NFR-7 in one place, because it is the requirement most likely to be broken by a well-meaning refactor.

| What must keep working | How it is guaranteed | Test |
|---|---|---|
| A session created before the upgrade opens | its `model` string is alias-mapped at read time, not migrated in a batch | fixture sessions, one per legacy id form |
| The Databricks agent config is unchanged | a golden-file comparison against today's output | `test_agent_config_golden` (byte equality) |
| `config_for` callers still work during the transition | it remains as a one-line delegate to the resolver until P7 | a grep test counts its definitions |
| The exam suite's numbers stay comparable | the config, the working agreement and the tool list are untouched | re-run two variants and compare to `exams/results/` |
| A stored `databricks-system.ai.gpt-oss-120b` (dash form) resolves | the alias map includes the form the old string surgery produced | property test over every historical form |
| Demo mode needs no database | the memory store is wired when `agent_mode="fake"` | the existing API tests run unchanged |

The golden-file test is the important one. Everything in [README findings](../../README.md) was measured
with one exact agent configuration; if it changes by a byte, the numbers are no longer comparable to
anything in this repository.

---

## Scale

| Dimension | Measured assumption | Behaviour | When to revisit |
|---|---|---|---|
| models per catalogue | ~40 (5 gateway + 3 external providers × ~10) | one query, no virtualisation | at 200 models, add windowing (E-26) |
| health rows | 200 models × 96 probes/day = 19 200/day | 7-day retention ≈ 135 k rows | at 1 M rows, partition by month |
| discovery calls | 1 per 300 s per process | a shared watermark when replicas > 1 | at 2 replicas |
| credential decryptions | 1 per session start + 1 per switch | a token cache keyed by ref, cleared on revoke | if a switch becomes hot |
| keys per user | 1 per provider (unique index) | rotation is insert + revoke | if a user needs two accounts for one provider |

---

## The six CI gates

```bash
# 1. layer rule (C-2): no vendor branch in the core
rg "== ['\"](databricks|openai|anthropic|google_vertex)['\"]" api/domain api/services   # expect: nothing

# 2. one resolver (C-3)
rg -c "def config_for" api ; rg "KNOWN_ENDPOINTS" api                                     # expect: 1 ; nothing

# 3. limits guard (C-4), now over the registry rather than over Settings
pytest -k "limits or offered"

# 4. the spec's diagrams are aligned
node scripts/verify-spec-ascii.mjs ../../../specs/005-llm-models

# 5. every internal link and anchor resolves
node scripts/verify-spec-links.mjs ../../../specs/005-llm-models

# 6. every Mermaid block parses
node scripts/verify-spec-mermaid.mjs ../../../specs/005-llm-models
```

---

## The five tests to write first

If only five tests get written, these are the five, in this order — each one catches a class of bug
that is expensive to find in production.

1. **E-12** — two users, two keys, a fake provider that records headers. Cross-tenant leaks are
   incidents, not bugs.
2. **E-18** — a switch mid-turn does not rewrite the earlier pin. Provenance is the product.
3. **E-4** — a cap error lowers the stored cap and never raises it. The most common invisible failure.
4. **E-14** — the app boots and serves models with no database. The most likely deployment surprise.
5. **P4's golden file** — the Databricks agent config is byte-identical to today's. The regression that
   would silently invalidate the measurements in this repository.
