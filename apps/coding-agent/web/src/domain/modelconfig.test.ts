import { describe, expect, it } from "vitest";
import {
  defaultCandidates, externalProviders, formatTokens, modelsOf, parseTokens, storageLine,
  validateNewModel, type ModelConfig,
} from "./modelconfig";

describe("parseTokens", () => {
  it.each([["128k", 128000], ["1M", 1000000], ["1.5k", 1500], ["200,000", 200000], [" 8 K ", 8000], ["4096", 4096]])(
    "%s -> %i", (text, n) => expect(parseTokens(text as string)).toBe(n));
  it.each(["", "k", "-5", "abc", "1x", "0"])("refuses %j", (text) => expect(parseTokens(text)).toBeNaN());
});

describe("formatTokens", () => {
  it.each([[128000, "128k"], [1000000, "1M"], [1500, "1.5k"], [900, "900"], [0, "—"], [Number.NaN, "—"]])(
    "%s -> %s", (n, text) => expect(formatTokens(n as number)).toBe(text));
});

describe("validateNewModel", () => {
  const ok = { model: "google/gemini-3.8-flash", name: "", context: "1M", output: "30k" };
  it("accepts a well formed model", () => {
    const r = validateNewModel(ok);
    expect(r.errors).toEqual({});
    expect(r.context).toBe(1000000);
    expect(r.output).toBe(30000);
  });
  it("names each wrong field", () => {
    expect(validateNewModel({ ...ok, model: "" }).errors.model).toMatch(/model name/);
    expect(validateNewModel({ ...ok, model: "bad name" }).errors.model).toMatch(/letters/);
    expect(validateNewModel({ ...ok, model: "../x" }).errors.model).toBeTruthy();
    expect(validateNewModel({ ...ok, context: "lots" }).errors.context).toMatch(/128k/);
    expect(validateNewModel({ ...ok, output: "2M" }).errors.output).toMatch(/larger/);
  });
});

describe("storageLine", () => {
  it("says a database save will persist, and anything else will not", () => {
    expect(storageLine({ source: "database", location: "ep/db", canSave: true })).toEqual({ tone: "ok", text: "Saved in the database (ep/db)." });
    expect(storageLine({ source: "seed", location: "", canSave: false }).tone).toBe("warn");
    expect(storageLine({ source: "degraded", location: "", canSave: false }).text).toMatch(/unreachable/);
    expect(storageLine({ source: "memory", location: "", canSave: true }).text).toMatch(/lost on restart/);
  });
});

const model = (id: string, provider: string, over: Partial<ModelConfig["models"][number]> = {}) => ({
  id, name: id.split("/").pop()!, provider, providerName: provider, endpoint: id, state: "available",
  enabled: true, selectable: true, isDefault: false, managed: provider === "databricks",
  capability: "tools", origin: "database", refusal: "",
  limits: { context: 1, output: 1, evidence: "documented", source: "" },
  credential: { kind: "api_key", source: "none", hint: "" }, ...over,
});

const cfg: ModelConfig = {
  source: "database", location: "", canConfigure: true, canSave: true, reason: "", externalAllowed: true,
  vault: { mode: "env", available: true }, default: "openai/a",
  providers: [
    { id: "openai", name: "OpenAI", kind: "openai", enabled: true, baseUrl: "", wire: "openai", external: true, hasKey: false, example: "gpt-4.1" },
    { id: "databricks", name: "Databricks", kind: "databricks", enabled: true, baseUrl: "", wire: "serving", external: false, hasKey: false, example: "" },
    { id: "anthropic", name: "Anthropic", kind: "anthropic", enabled: true, baseUrl: "", wire: "anthropic", external: true, hasKey: true, example: "" },
  ],
  models: [model("openai/b", "openai"), model("openai/a", "openai", { isDefault: true }),
    model("openai/off", "openai", { enabled: false }), model("databricks/x", "databricks")],
};

describe("selectors", () => {
  it("lists only external providers, alphabetically", () =>
    expect(externalProviders(cfg).map((p) => p.id)).toEqual(["anthropic", "openai"]));
  it("puts the default model first within a provider", () =>
    expect(modelsOf(cfg, "openai").map((m) => m.id)).toEqual(["openai/a", "openai/b", "openai/off"]));
  it("offers only switched-on, selectable models as the default", () =>
    expect(defaultCandidates(cfg).map((m) => m.id)).not.toContain("openai/off"));
});
