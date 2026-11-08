/** Rules for the model configuration screen: pure, so the form and the server agree and tests are cheap. */

export interface ConfigModel {
  id: string; name: string; provider: string; providerName: string; endpoint: string;
  state: string; enabled: boolean; selectable: boolean; isDefault: boolean; managed: boolean;
  capability: string; origin: string; refusal: string;
  limits: { context: number; output: number; evidence: string; source: string };
  credential: { kind: string; source: string; hint: string };
}

export interface ConfigProvider {
  id: string; name: string; kind: string; enabled: boolean; baseUrl: string; wire: string;
  external: boolean; hasKey: boolean; example: string;
}

export interface ModelConfig {
  source: string; location: string; canConfigure: boolean; canSave: boolean; reason: string;
  externalAllowed: boolean; vault: { mode: string; available: boolean };
  default: string; providers: ConfigProvider[]; models: ConfigModel[];
}

/** "128k" -> 128000, "1m" -> 1000000, "200,000" -> 200000. Anything else is NaN, never a guess. */
export function parseTokens(text: string): number {
  const m = /^\s*([0-9][0-9_,]*(?:\.[0-9]+)?)\s*([kKmM]?)\s*$/.exec(text);
  if (!m) return Number.NaN;
  const base = Number(m[1].replace(/[_,]/g, ""));
  const scale = m[2].toLowerCase() === "m" ? 1_000_000 : m[2].toLowerCase() === "k" ? 1_000 : 1;
  const n = Math.round(base * scale);
  return Number.isFinite(n) && n > 0 ? n : Number.NaN;
}

/** 128000 -> "128k", 1000000 -> "1M", 1500 -> "1.5k". Round numbers read as people write them. */
export function formatTokens(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return "—";
  if (n >= 1_000_000) return `${+(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${+(n / 1_000).toFixed(1)}k`;
  return String(n);
}

export interface NewModelForm { model: string; name: string; context: string; output: string }
export type FormErrors = Partial<Record<keyof NewModelForm, string>>;

const NAME = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,118}$/;

/** The same checks the server makes, so a mistake is named before the round trip. */
export function validateNewModel(f: NewModelForm): { errors: FormErrors; context: number; output: number } {
  const errors: FormErrors = {};
  const model = f.model.trim();
  if (!model) errors.model = "Enter the model name the provider uses.";
  else if (!NAME.test(model) || model.includes("..") || model.endsWith("/"))
    errors.model = "Use letters, digits and . _ : / - only.";
  const context = parseTokens(f.context);
  const output = parseTokens(f.output);
  if (Number.isNaN(context)) errors.context = "Enter a number such as 128k or 1M.";
  if (Number.isNaN(output)) errors.output = "Enter a number such as 8k.";
  if (!errors.context && !errors.output && output > context)
    errors.output = "The output limit cannot be larger than the context window.";
  return { errors, context, output };
}

/** One line that says where the configuration is kept, and whether a change will survive a restart. */
export function storageLine(c: Pick<ModelConfig, "source" | "location" | "canSave">): { tone: "ok" | "warn"; text: string } {
  if (c.source === "database") return { tone: "ok", text: `Saved in the database (${c.location || "Postgres"}).` };
  if (c.source === "memory") return { tone: "warn", text: "Demo mode: changes are kept in memory and are lost on restart." };
  if (c.source === "degraded") return { tone: "warn", text: "The model database is unreachable. You can read the catalogue, not change it." };
  return { tone: "warn", text: "No model database is configured, so changes cannot be saved." };
}

/** External providers first, in a stable order; the built-in workspace provider is not editable. */
export function externalProviders(c: ModelConfig): ConfigProvider[] {
  return c.providers.filter((p) => p.external).sort((a, b) => a.name.localeCompare(b.name));
}

export function modelsOf(c: ModelConfig, providerId: string): ConfigModel[] {
  return c.models.filter((m) => m.provider === providerId)
    .sort((a, b) => Number(b.isDefault) - Number(a.isDefault) || a.name.localeCompare(b.name));
}

/** Models that may be chosen as the default: switched on and offered by the picker. */
export function defaultCandidates(c: ModelConfig): ConfigModel[] {
  return c.models.filter((m) => m.enabled && m.selectable)
    .sort((a, b) => a.providerName.localeCompare(b.providerName) || a.name.localeCompare(b.name));
}
