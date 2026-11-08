/** Deep links: what the address bar says about what is on screen. Pure: no React, no DOM.
 *
 * One grammar, in the hash (the hash never reaches the server, so any host or proxy serves it):
 *
 *   #/notebook/Users/me@x.com/agent_scratch/etl?cell=3     a notebook, optionally at a cell
 *   #/file/Users/me@x.com/notes.py                         a workspace file
 *   #/table/main.sales.orders                              a Unity Catalog table
 *   #/session/<id>                                         a conversation
 *   #/settings/models   #/settings/providers               the settings screen, on a tab
 *   (empty)                                                 the start page
 *
 * Paths are written the way people write them, so a link can be read and typed: `/` and `@` stay,
 * everything else that matters is percent-encoded per segment. `parse(format(r))` is `r` for every
 * route (the tests hold that), and anything unrecognised parses to the empty route rather than throwing:
 * a stale link must open the app, not a blank page.
 */
export type DocRouteKind = "notebook" | "file" | "table";

export interface Route {
  doc: { kind: DocRouteKind; ref: string } | null;
  /** 1-based cell number within `doc`. */
  cell: number | null;
  session: string | null;
  settings: "providers" | "models" | null;
}

export const EMPTY_ROUTE: Route = { doc: null, cell: null, session: null, settings: null };

const encodeSegment = (s: string) => encodeURIComponent(s).replace(/%40/g, "@").replace(/%3A/gi, ":");
const encodePath = (p: string) => p.replace(/^\/+/, "").split("/").map(encodeSegment).join("/");
const decodeSegment = (s: string) => { try { return decodeURIComponent(s); } catch { return s; } };

export function formatRoute(r: Route): string {
  if (r.settings) return `#/settings/${r.settings}`;
  if (r.doc) {
    const { kind, ref } = r.doc;
    const body = kind === "table" ? encodeSegment(ref) : encodePath(ref);
    const cell = r.cell && r.cell > 0 && kind === "notebook" ? `?cell=${Math.floor(r.cell)}` : "";
    return `#/${kind}/${body}${cell}`;
  }
  if (r.session) return `#/session/${encodeSegment(r.session)}`;
  return "";
}

export function parseRoute(hash: string): Route {
  const text = (hash ?? "").replace(/^#/, "");
  // The first release wrote `#settings/models`; links already shared keep working.
  const legacy = /^settings\/(models|providers)$/.exec(text);
  if (legacy) return { ...EMPTY_ROUTE, settings: legacy[1] as "models" | "providers" };
  const [pathPart, query = ""] = text.split("?", 2);
  const parts = pathPart.replace(/^\/+/, "").split("/");
  const head = parts[0];
  const rest = parts.slice(1);
  if (head === "settings") {
    return { ...EMPTY_ROUTE, settings: rest[0] === "models" ? "models" : "providers" };
  }
  if (head === "session" && rest.length === 1 && rest[0]) {
    return { ...EMPTY_ROUTE, session: decodeSegment(rest[0]) };
  }
  if ((head === "notebook" || head === "file") && rest.length > 0 && rest.join("")) {
    const ref = `/${rest.map(decodeSegment).join("/")}`;
    const n = Number(new URLSearchParams(query).get("cell"));
    return { ...EMPTY_ROUTE, doc: { kind: head, ref }, cell: head === "notebook" && Number.isInteger(n) && n > 0 ? n : null };
  }
  if (head === "table" && rest.length === 1 && rest[0]) {
    return { ...EMPTY_ROUTE, doc: { kind: "table", ref: decodeSegment(rest[0]) } };
  }
  return EMPTY_ROUTE;
}

export const sameRoute = (a: Route, b: Route): boolean => formatRoute(a) === formatRoute(b);

/** The absolute URL of a route on this page, for "copy link". */
export function linkTo(r: Route, base: { origin: string; pathname: string }): string {
  return `${base.origin}${base.pathname}${formatRoute(r)}`;
}
