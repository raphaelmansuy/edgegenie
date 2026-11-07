/** The model catalogue as pure data rules: grouping, ordering, labelling, availability copy.
 *
 * No React, no fetch, no `Date.now()`. Everything here is a function over a fixture list, so the
 * picker's order is a **test** rather than an accident of iteration (spec 005 D14). The same functions
 * are used by the picker, the inspector and the palette, so the three views of one value cannot
 * disagree.
 *
 * The wire shape is `/api/llm/models`; `ModelSpec` mirrors it field for field.
 */

export type ModelState =
  | "available"
  | "degraded"
  | "unauthorised"
  | "not_served"
  | "not_enabled"
  | "unknown";

export type Capability = "tools" | "tools_and_reasoning" | "chat_only";

export type LimitEvidence = "measured" | "documented" | "default";

export interface ModelLimits {
  context: number;
  output: number;
  evidence: LimitEvidence;
  source: string;
  /** True when nothing is known: the picker must say so rather than present the number as a fact. */
  unverified: boolean;
}

export interface ModelCredential {
  kind: string;
  source: "workspace_token" | "user" | "workspace" | "env" | "none";
  hint: string;
}

export interface ModelSpec {
  id: string;
  name: string;
  provider: string;
  providerName: string;
  wire: string;
  capability: Capability;
  state: ModelState;
  selectable: boolean;
  /** Why this model may not be offered, when it may not. Empty means "no reason to refuse". */
  refusal: string;
  detail: string;
  checkedAt: number | null;
  limits: ModelLimits;
  credential: ModelCredential;
  group: string;
  origin: string;
  endpoint: string;
}

export interface CatalogueResponse {
  available: ModelSpec[];
  default: string;
  source: "seed" | "memory" | "database" | "degraded" | "static";
  updatedAt: string;
}

/* ------------------------------------------------------------------ labels */

/** The one place a label is derived. `id.split("/").pop()` produced two naming conventions in one
 *  dropdown (01 E8); this returns the catalogue's display name, and falls back to a readable form. */
export function label(spec: ModelSpec): string {
  if (spec.name && spec.name.trim()) return spec.name;
  return prettyId(spec.id);
}

/** A last-resort label from an id, used only when the catalogue supplied no name. */
export function prettyId(id: string): string {
  const tail = id.split("/").slice(1).join("/") || id;
  return tail.replace(/^databricks-/, "");
}

/** 128000 -> "128k", 1000000 -> "1M". A cap a person can compare at a glance. */
export function prettyTokens(n: number): string {
  if (!Number.isFinite(n) || n <= 0) return "—";
  if (n >= 1_000_000) {
    const m = n / 1_000_000;
    return `${Number.isInteger(m) ? m : m.toFixed(1)}M`;
  }
  if (n >= 1_000) {
    const k = n / 1_000;
    return `${Number.isInteger(k) ? k : Math.round(k)}k`;
  }
  return String(n);
}

/** The limits column: what it costs, and how sure we are. Never a bare number without its evidence. */
export function limitsCopy(spec: ModelSpec): string {
  const { limits } = spec;
  if (limits.unverified) return "limits unverified · capped at 64k / 4k";
  return `${prettyTokens(limits.context)} ctx · ${prettyTokens(limits.output)} out · ${limits.evidence}`;
}

/* ------------------------------------------------------------------ states */

/** Every state has copy and an action, exhaustively. A `Record` over the union, so adding a state
 *  without copy is a type error rather than a blank row. */
export const STATE_COPY: Record<ModelState, { glyph: string; word: string; tone: string }> = {
  available: { glyph: "○", word: "available", tone: "ok" },
  degraded: { glyph: "⚠", word: "degraded", tone: "warn" },
  unauthorised: { glyph: "⚠", word: "needs a new key", tone: "warn" },
  not_served: { glyph: "◌", word: "not served here", tone: "muted" },
  not_enabled: { glyph: "◌", word: "not enabled here", tone: "muted" },
  unknown: { glyph: "?", word: "never probed", tone: "muted" },
};

/** Why a model cannot be chosen, in words that name the next action (FR-16…FR-20, U7).
 *
 * The order of the checks is the design: a **missing key** is reported before the model's health,
 * because a key is something the user can add in this app and a provider outage is not (FR-19).
 * Then the refusal, then the state, then the capability.
 */
export function availabilityCopy(spec: ModelSpec): string {
  if (spec.refusal) return spec.refusal;
  if (needsKey(spec)) return `${spec.providerName} needs a key before this model can run.`;
  switch (spec.state) {
    case "not_enabled":
      return "Not enabled in this workspace. An account admin must enable it in the AI Gateway.";
    case "not_served":
      return "Not served in this workspace. Ask an admin, or resume this session with another model.";
    case "unauthorised":
      return spec.detail || "The provider refused the key. Replace it to use this model.";
    case "degraded":
      return spec.detail || "The provider is failing. Retry, or switch to another model.";
    case "unknown":
      return "Never probed. Choose it and the first turn will tell you.";
    default:
      break;
  }
  if (spec.capability === "chat_only") return "This model cannot call tools, which this agent needs.";
  return "Ready.";
}

/** True when this model needs a stored credential that is not present. */
export function needsKey(spec: ModelSpec): boolean {
  return spec.credential.kind !== "none" && spec.credential.source === "none";
}

/** The one predicate the picker uses. `selectable` comes from the server; a missing key is local. */
export function canChoose(spec: ModelSpec): boolean {
  return spec.selectable && !needsKey(spec);
}

/** The short provider tag at the right of a row. A one-word label, never the first word of a name
 *  (which produced "the" for "The demo agent"). */
export function providerTag(spec: ModelSpec): string {
  const tags: Record<string, string> = {
    databricks: "gateway",
    openai: "openai",
    anthropic: "anthropic",
    google_vertex: "vertex",
    fake: "demo",
  };
  return tags[spec.provider] ?? spec.provider;
}

/* ------------------------------------------------------------------ grouping */

export const GROUP_GATEWAY = "Databricks · AI Gateway";
export const GROUP_YOURS = "Your providers";
export const GROUP_WORKSPACE = "Workspace providers";
export const GROUP_UNAVAILABLE = "Not available here";
export const GROUP_DEMO = "Demo models";

/**
 * Rank order for groups (07 §Grouping and order). Deterministic: a list that reorders itself cannot
 * be learned.
 *
 * `spec.group` wins when the server set one — that is how demo mode gets its own honest group rather
 * than being passed off as a provider the user configured.
 */
export function groupOf(spec: ModelSpec): string {
  if (spec.group) return spec.group;
  if (spec.provider === "fake") return GROUP_DEMO;
  if (spec.provider === "databricks") {
    return spec.state === "not_enabled" || spec.state === "not_served" ? GROUP_UNAVAILABLE : GROUP_GATEWAY;
  }
  if (!canChoose(spec)) return GROUP_UNAVAILABLE;
  return spec.credential.source === "workspace" || spec.credential.source === "env"
    ? GROUP_WORKSPACE
    : GROUP_YOURS;
}

/** Group order, then "the current model first", then availability, then name (case-insensitively). */
const GROUP_RANK = [GROUP_GATEWAY, GROUP_DEMO, GROUP_YOURS, GROUP_WORKSPACE, GROUP_UNAVAILABLE];

const STATE_RANK: Record<ModelState, number> = {
  available: 0,
  unknown: 1,
  degraded: 2,
  unauthorised: 3,
  not_enabled: 4,
  not_served: 5,
};

export function orderModels(specs: ModelSpec[], current = ""): ModelSpec[] {
  return [...specs].sort((a, b) => {
    const ga = rank(GROUP_RANK, groupOf(a));
    const gb = rank(GROUP_RANK, groupOf(b));
    if (ga !== gb) return ga - gb;
    const cur = (s: ModelSpec) => (s.id === current ? 0 : 1);
    if (cur(a) !== cur(b)) return cur(a) - cur(b);
    const sa = STATE_RANK[a.state];
    const sb = STATE_RANK[b.state];
    if (sa !== sb) return sa - sb;
    return label(a).toLowerCase().localeCompare(label(b).toLowerCase());
  });
}

function rank(order: string[], value: string): number {
  const at = order.indexOf(value);
  return at === -1 ? order.length : at;
}

export interface Group {
  name: string;
  rows: SpecRow[];
  /** How many rows in the whole group are choosable — the header's "2 of 3". */
  choosable: number;
  total: number;
  /** A group with no match collapses to a count line **inside its own header**, never disappearing. */
  matched: boolean;
  collapsed: boolean;
}

export interface SpecRow {
  spec: ModelSpec;
  /** Why the name matched, when a search is active (U3: the footer states it). */
  matchedOn: "name" | "provider" | "id" | "";
}

export interface GroupOptions {
  current?: string;
  query?: string;
  /** Groups that start collapsed even when they have rows. The unavailable group, by default. */
  collapsedGroups?: string[];
}

/**
 * The picker's model of the world: every group present, always, in a stable order.
 *
 * A group is never missing — during a search each appears with a count, even at zero matches, so a
 * user learns a provider exists before discovering it has nothing to offer (07 U1).
 */
export function groupModels(specs: ModelSpec[], options: GroupOptions = {}): Group[] {
  const collapsed = new Set(options.collapsedGroups ?? [GROUP_UNAVAILABLE]);
  const query = (options.query ?? "").trim().toLowerCase();
  const ordered = orderModels(specs, options.current ?? "");

  const buckets = new Map<string, SpecRow[]>();
  for (const spec of ordered) {
    const name = groupOf(spec);
    const matchedOn = query ? matchOf(spec, query) : "";
    if (query && !matchedOn) continue;
    const rows = buckets.get(name) ?? [];
    rows.push({ spec, matchedOn });
    buckets.set(name, rows);
  }

  const names = new Set<string>([...buckets.keys()]);
  // A group that exists in the catalogue but has no match still gets a count line in search.
  if (query) for (const spec of specs) names.add(groupOf(spec));

  return [...names]
    .sort((a, b) => rank(GROUP_RANK, a) - rank(GROUP_RANK, b) || a.localeCompare(b))
    .map((name) => {
      const rows = buckets.get(name) ?? [];
      const all = specs.filter((s) => groupOf(s) === name);
      return {
        name,
        rows,
        choosable: all.filter(canChoose).length,
        total: all.length,
        matched: rows.length > 0,
        collapsed: collapsed.has(name) && !(query && rows.length > 0),
      };
    })
    .filter((g) => g.total > 0);
}

/** Which field matched, so the footer can say why (U3). Empty means "no match". */
export function matchOf(spec: ModelSpec, query: string): SpecRow["matchedOn"] {
  const q = query.toLowerCase();
  if (label(spec).toLowerCase().includes(q)) return "name";
  if (spec.providerName.toLowerCase().includes(q)) return "provider";
  if (spec.id.toLowerCase().includes(q) || spec.endpoint.toLowerCase().includes(q)) return "id";
  return "";
}

/** The footer's account of the search: "gemini · matched name · 2 selectable · 1 unavailable". */
export function searchSummary(groups: Group[], query: string): string {
  if (!query.trim()) {
    const all = groups.flatMap((g) => g.rows.map((r) => r.spec));
    const usable = all.filter(canChoose).length;
    return `${all.length} models · ${usable} selectable`;
  }
  const rows = groups.flatMap((g) => g.rows);
  const usable = rows.filter((r) => canChoose(r.spec)).length;
  const why = rows.find((r) => r.matchedOn)?.matchedOn ?? "name";
  const parts = [`${rows.length} match${rows.length === 1 ? "" : "es"}`];
  if (rows.length) parts.push(`matched ${why}`);
  parts.push(`${usable} selectable`);
  if (rows.length - usable > 0) parts.push(`${rows.length - usable} unavailable`);
  return parts.join(" · ");
}

/** Every row in order, for the keyboard model: arrow keys cross group boundaries (U2). */
export function flatRows(groups: Group[]): SpecRow[] {
  return groups.filter((g) => !g.collapsed).flatMap((g) => g.rows);
}

/** The "updated Nm ago" footer (U10). Pure: the caller supplies `now`. */
export function freshness(iso: string, now: number): string {
  const at = Date.parse(iso);
  if (!Number.isFinite(at)) return "";
  const seconds = Math.max(0, Math.round((now - at) / 1000));
  if (seconds < 10) return "updated just now";
  if (seconds < 60) return `updated ${seconds}s ago`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `updated ${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `updated ${hours}h ago`;
  return `updated ${Math.round(hours / 24)}d ago`;
}

/** The header notice for a reduced-capability catalogue (C-5, 07 screen 7a). */
export function sourceNotice(source: CatalogueResponse["source"]): string {
  switch (source) {
    case "degraded":
      return "Keys cannot be saved: the model database is unreachable. Databricks models work. "
        + "External models need a key.";
    case "seed":
      return "This app is serving the built-in catalogue. Keys cannot be saved without a database.";
    case "static":
      return "This app is serving its configured models only.";
    default:
      return "";
  }
}

/** The default model: the catalogue's, or the first choosable row. Never an invented id. */
export function defaultModel(cat: CatalogueResponse | null): string {
  if (!cat) return "";
  if (cat.default) return cat.default;
  const first = orderModels(cat.available).find(canChoose);
  return first?.id ?? "";
}
