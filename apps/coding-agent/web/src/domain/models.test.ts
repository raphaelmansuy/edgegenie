/** The catalogue rules, unit-tested. No React: these are the assertions the picker relies on.
 *
 * The order, the labels and the copy are the design (07 §Grouping, §Copy), so each one is a test
 * rather than a review comment.
 */
import { describe, expect, it } from "vitest";
import {
  canChoose,
  availabilityCopy,
  defaultModel,
  flatRows,
  freshness,
  groupModels,
  groupOf,
  GROUP_DEMO,
  GROUP_GATEWAY,
  GROUP_UNAVAILABLE,
  GROUP_YOURS,
  label,
  limitsCopy,
  matchOf,
  needsKey,
  orderModels,
  prettyTokens,
  providerTag,
  searchSummary,
  sourceNotice,
  STATE_COPY,
  type CatalogueResponse,
  type ModelSpec,
  type ModelState,
} from "./models";

const spec = (over: Partial<ModelSpec> = {}): ModelSpec => ({
  id: "databricks/databricks-llama-4-maverick",
  name: "llama-4-maverick",
  provider: "databricks",
  providerName: "Databricks AI Gateway",
  wire: "serving",
  capability: "tools",
  state: "available",
  selectable: true,
  refusal: "",
  detail: "",
  checkedAt: null,
  limits: { context: 128_000, output: 8_000, evidence: "measured", source: "§3.2", unverified: false },
  credential: { kind: "none", source: "workspace_token", hint: "" },
  group: "",
  origin: "seed",
  endpoint: "databricks-llama-4-maverick",
  ...over,
});

const gemini = spec({
  id: "google_vertex/google/gemini-3.8-flash",
  name: "gemini-3.8-flash",
  provider: "google_vertex",
  providerName: "Google Vertex AI",
  wire: "vertex_native",
  capability: "tools_and_reasoning",
  state: "available",
  limits: { context: 1_000_000, output: 30_000, evidence: "documented", source: "template", unverified: false },
  credential: { kind: "service_account_json", source: "user", hint: "service account …7f3a" },
  endpoint: "google/gemini-3.8-flash",
});

const openaiNoKey = spec({
  id: "openai/gpt-4.1",
  name: "gpt-4.1",
  provider: "openai",
  providerName: "OpenAI",
  wire: "openai",
  state: "unknown",
  limits: { context: 128_000, output: 16_384, evidence: "documented", source: "docs", unverified: false },
  credential: { kind: "api_key", source: "none", hint: "" },
  endpoint: "gpt-4.1",
});

const gated = spec({
  id: "databricks/databricks-claude-sonnet-4-5",
  name: "claude-sonnet-4-5",
  state: "not_enabled",
  selectable: false,
  endpoint: "databricks-claude-sonnet-4-5",
});

describe("labels", () => {
  it("uses the catalogue's display name, never a raw id", () => {
    expect(label(spec())).toBe("llama-4-maverick");
    expect(label({ ...spec(), name: "" })).toBe("llama-4-maverick");
  });

  it("formats token counts so two caps compare at a glance", () => {
    expect(prettyTokens(8_000)).toBe("8k");
    expect(prettyTokens(128_000)).toBe("128k");
    expect(prettyTokens(1_000_000)).toBe("1M");
    expect(prettyTokens(30_000)).toBe("30k");
    expect(prettyTokens(1_500_000)).toBe("1.5M");
    expect(prettyTokens(0)).toBe("—");
  });

  it("never shows a limit without its evidence", () => {
    expect(limitsCopy(spec())).toBe("128k ctx · 8k out · measured");
    expect(limitsCopy({ ...spec(), limits: { ...spec().limits, unverified: true } }))
      .toContain("unverified");
  });
});

describe("states and copy", () => {
  it("has copy for every state in the union", () => {
    const states: ModelState[] = ["available", "degraded", "unauthorised", "not_served", "not_enabled", "unknown"];
    for (const s of states) {
      expect(STATE_COPY[s].glyph).toBeTruthy();
      expect(STATE_COPY[s].word).toBeTruthy();
    }
  });

  it("names the admin action for a gated model instead of hiding it", () => {
    expect(availabilityCopy(gated)).toMatch(/admin must enable/i);
  });

  it("distinguishes no key from no grant", () => {
    expect(needsKey(openaiNoKey)).toBe(true);
    expect(availabilityCopy(openaiNoKey)).toMatch(/needs a key/i);
    expect(availabilityCopy({ ...openaiNoKey, refusal: "you do not have access" }))
      .toMatch(/do not have access/i);
  });

  it("prefers the provider's own words when it has them", () => {
    // `unauthorised` means a key EXISTS and was refused, so its source is not "none": the two states
    // are different problems with different actions.
    const stale = {
      ...openaiNoKey,
      state: "unauthorised" as const,
      detail: "401 Unauthorized: Incorrect API key provided.",
      credential: { kind: "api_key", source: "user" as const, hint: "api key …9c41" },
    };
    expect(needsKey(stale)).toBe(false);
    expect(availabilityCopy(stale)).toBe("401 Unauthorized: Incorrect API key provided.");
  });

  it("refuses a chat-only model for a tool-calling agent", () => {
    const chat = { ...spec(), capability: "chat_only" as const, selectable: false };
    expect(availabilityCopy(chat)).toMatch(/cannot call tools/i);
  });
});

describe("grouping and order", () => {
  it("puts the gateway first, then demo, then the user's providers, then the unavailable", () => {
    const groups = groupModels([openaiNoKey, gated, gemini, spec()]);
    expect(groups.map((g) => g.name)).toEqual([GROUP_GATEWAY, GROUP_YOURS, GROUP_UNAVAILABLE]);
  });

  it("gives the demo agent its own group rather than passing it off as a provider", () => {
    const demo = spec({ id: "fake/model-a", name: "model-a", provider: "fake", providerName: "The demo agent", wire: "fake" });
    const groups = groupModels([demo, spec()]);
    expect(groups.map((g) => g.name)).toEqual([GROUP_GATEWAY, GROUP_DEMO]);
  });

  it("tags a provider with one word, never the first word of its name", () => {
    expect(providerTag(gemini)).toBe("vertex");
    expect(providerTag(spec())).toBe("gateway");
    expect(providerTag(spec({ id: "fake/x", provider: "fake", providerName: "The demo agent" }))).toBe("demo");
  });

  it("puts the current model first inside its group", () => {
    const groups = groupModels([spec(), spec({ id: "databricks/a", name: "aaa", endpoint: "a" })],
      { current: "databricks/databricks-llama-4-maverick" });
    expect(groups[0].rows[0].spec.name).toBe("llama-4-maverick");
  });

  it("collapses the unavailable group by default but never removes it", () => {
    const groups = groupModels([spec(), gated]);
    const unavailable = groups.find((g) => g.name === GROUP_UNAVAILABLE);
    expect(unavailable).toBeTruthy();
    expect(unavailable?.collapsed).toBe(true);
  });

  it("keeps a group present with a count even when the search matches nothing in it", () => {
    const groups = groupModels([spec(), gemini], { query: "gemin" });
    const gateway = groups.find((g) => g.name === GROUP_GATEWAY);
    expect(gateway).toBeTruthy();
    expect(gateway?.matched).toBe(false);
    expect(gateway?.total).toBe(1);
  });

  it("expands a collapsed group when a query matches inside it", () => {
    const groups = groupModels([spec(), gated], { query: "claude" });
    const unavailable = groups.find((g) => g.name === GROUP_UNAVAILABLE);
    expect(unavailable?.collapsed).toBe(false);
    expect(unavailable?.rows.map((r) => r.spec.name)).toEqual(["claude-sonnet-4-5"]);
  });

  it("filters by name, provider and id, and says which matched", () => {
    expect(matchOf(gemini, "gemin")).toBe("name");
    expect(matchOf(gemini, "vertex")).toBe("provider");
    expect(matchOf(gemini, "google/")).toBe("id");
    expect(matchOf(gemini, "zzz")).toBe("");
  });

  it("is a deterministic order for the same input", () => {
    const once = orderModels([spec(), gemini, openaiNoKey]).map((s) => s.id);
    const twice = orderModels([openaiNoKey, gemini, spec()]).map((s) => s.id);
    expect(once).toEqual(twice);
  });

  it("counts what is choosable per group, for the header's '1 of 2'", () => {
    const groups = groupModels([spec(), gated]);
    const gateway = groups.find((g) => g.name === GROUP_GATEWAY)!;
    // The gated model is `not_enabled`, so it belongs to the unavailable group: the gateway holds one
    // row and that row is choosable. The header's count must reflect the group, not the catalogue.
    expect(gateway.total).toBe(1);
    expect(gateway.choosable).toBe(1);
    const unavailable = groups.find((g) => g.name === GROUP_UNAVAILABLE)!;
    expect(unavailable.total).toBe(1);
    expect(unavailable.choosable).toBe(0);
  });

  it("flattens to the rows a keyboard walks, skipping collapsed groups", () => {
    const groups = groupModels([spec(), gemini, gated]);
    expect(flatRows(groups).map((r) => r.spec.name)).toEqual(["llama-4-maverick", "gemini-3.8-flash"]);
  });

  it("puts a model with no key among the unavailable, not among the usable", () => {
    expect(groupOf(openaiNoKey)).toBe(GROUP_UNAVAILABLE);
    expect(canChoose(openaiNoKey)).toBe(false);
  });
});

describe("the footer", () => {
  it("states why the match happened", () => {
    const groups = groupModels([gemini], { query: "gemin" });
    expect(searchSummary(groups, "gemin")).toContain("matched name");
  });

  it("counts selectable and unavailable separately", () => {
    const groups = groupModels([spec(), gated]);
    expect(searchSummary(groups, "")).toContain("1 selectable");
  });

  it("says how stale the catalogue is rather than pretending it is current", () => {
    const now = Date.parse("2026-11-07T10:00:30Z");
    expect(freshness("2026-11-07T10:00:29Z", now)).toBe("updated just now");
    expect(freshness("2026-11-07T10:00:18Z", now)).toBe("updated 12s ago");
    expect(freshness("2026-11-07T09:58:30Z", now)).toBe("updated 2m ago");
    expect(freshness("2026-11-07T07:00:30Z", now)).toBe("updated 3h ago");
    expect(freshness("not a date", now)).toBe("");
  });
});

describe("degradation", () => {
  it("explains a degraded catalogue in words a user can act on", () => {
    expect(sourceNotice("degraded")).toMatch(/database is unreachable/i);
    expect(sourceNotice("degraded")).toMatch(/Databricks models work/i);
    expect(sourceNotice("database")).toBe("");
  });
});

describe("the default", () => {
  it("uses the catalogue's default and never invents an id", () => {
    const cat: CatalogueResponse = {
      available: [spec(), gemini], default: "google_vertex/google/gemini-3.8-flash",
      source: "database", updatedAt: "2026-11-07T10:00:00Z",
    };
    expect(defaultModel(cat)).toBe("google_vertex/google/gemini-3.8-flash");
    expect(defaultModel({ ...cat, default: "" })).toBe("databricks/databricks-llama-4-maverick");
    expect(defaultModel(null)).toBe("");
  });

  it("falls back to the first choosable model when the default is not usable", () => {
    const cat: CatalogueResponse = {
      available: [openaiNoKey, spec()], default: "", source: "seed",
      updatedAt: "2026-11-07T10:00:00Z",
    };
    expect(defaultModel(cat)).toBe("databricks/databricks-llama-4-maverick");
  });
});
