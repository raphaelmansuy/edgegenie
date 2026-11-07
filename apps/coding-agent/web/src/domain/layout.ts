/** The shell's geometry: the only place that decides a column width.
 *
 * Pure, no React, no DOM. Every number a zone can take, every bound a drag must respect, and the
 * whole of "what survives a reload" lives here, so it can be tested without a browser and cannot
 * drift between the separator, the CSS and the persistence layer (specs/001-perfect-shell, SH-G3).
 *
 * The one rule this module exists to enforce: the centre column is never sacrificed. A panel may be
 * wide because the user dragged it, but never so wide that the work area drops below CENTRE_MIN.
 */

export type RailTab = "sessions" | "files" | "catalog";
export type Mode = "wide" | "mid" | "narrow";
export type Zone = "rail" | "inspector";

export interface Layout {
  railWidth: number;
  inspectorWidth: number;
  railVisible: boolean;
  inspectorVisible: boolean;
  railTab: RailTab;
}

/** Bounds. One definition each: the separator, the CSS and the parser all read these. */
export const RAIL_MIN = 200;
export const RAIL_DEFAULT = 276;
export const INSPECTOR_MIN = 260;
export const INSPECTOR_MAX = 520;
export const INSPECTOR_DEFAULT = 340;
/** Below this the centre column stops being usable for code. It wins every argument. */
export const CENTRE_MIN = 480;
/** A panel may never take more than this share of the window. */
export const MAX_SHARE = 0.4;
/** Steps for the keyboard, in px. Shift is the coarse step. */
export const KEY_STEP = 8;
export const KEY_STEP_COARSE = 64;

export const RAIL_TABS: readonly RailTab[] = ["sessions", "files", "catalog"];

export const DEFAULTS: Layout = {
  railWidth: RAIL_DEFAULT,
  inspectorWidth: INSPECTOR_DEFAULT,
  railVisible: true,
  inspectorVisible: true,
  railTab: "sessions",
};

export const STORAGE_KEY = "coding-agent:layout:v1";

/** wide: three columns · mid: inspector is an overlay · narrow: both are overlays. */
export function modeFor(viewport: number): Mode {
  if (!Number.isFinite(viewport) || viewport <= 0) return "wide";
  return viewport <= 820 ? "narrow" : viewport <= 1180 ? "mid" : "wide";
}

/** The widest a zone may be, given the other zone and the window. May be below the minimum in a tiny
 *  window; callers clamp to the minimum first and accept the overflow, since a 200 px panel in a 300 px
 *  window is the user's problem, not the arithmetic's. */
export function maxWidth(zone: Zone, layout: Layout, viewport: number): number {
  // A zone that is an overlay (mid/narrow) takes no column, so it must not constrain the other one.
  const mode = modeFor(viewport);
  const takesColumn = (z: Zone) => (z === "rail"
    ? mode !== "narrow" && layout.railVisible
    : mode === "wide" && layout.inspectorVisible);
  const other = takesColumn(zone === "rail" ? "inspector" : "rail")
    ? (zone === "rail" ? layout.inspectorWidth : layout.railWidth)
    : 0;
  const share = Math.floor(viewport * MAX_SHARE);
  const byCentre = viewport - other - CENTRE_MIN;
  const cap = zone === "inspector" ? INSPECTOR_MAX : Number.POSITIVE_INFINITY;
  return Math.max(minWidth(zone), Math.min(share, byCentre, cap));
}

export function minWidth(zone: Zone): number {
  return zone === "rail" ? RAIL_MIN : INSPECTOR_MIN;
}

export function defaultWidth(zone: Zone): number {
  return zone === "rail" ? RAIL_DEFAULT : INSPECTOR_DEFAULT;
}

/** A width the zone is allowed to have. Integral, because a half pixel renders as a blurry divider. */
export function clampWidth(zone: Zone, want: number, viewport: number, layout: Layout = DEFAULTS): number {
  const lo = minWidth(zone);
  const hi = maxWidth(zone, layout, viewport);
  const w = Number.isFinite(want) ? Math.round(want) : defaultWidth(zone);
  return Math.max(lo, Math.min(w, Math.max(lo, hi)));
}

/** The value for grid-template-columns. This function is the only producer of that string. */
export function columns(layout: Layout, viewport: number): string {
  const mode = modeFor(viewport);
  // Overlays do not take a column: at mid and narrow a visible inspector is drawn over the work area.
  const rail = mode !== "narrow" && layout.railVisible;
  const inspector = mode === "wide" && layout.inspectorVisible;
  const parts: string[] = [];
  if (rail) parts.push(`${clampWidth("rail", layout.railWidth, viewport, layout)}px`);
  parts.push("minmax(0, 1fr)");
  if (inspector) parts.push(`${clampWidth("inspector", layout.inspectorWidth, viewport, layout)}px`);
  return parts.join(" ");
}

/** A drag or a keypress. `delta` is px: positive widens the zone. */
export function resizeBy(zone: Zone, layout: Layout, viewport: number, delta: number): Layout {
  const current = zone === "rail" ? layout.railWidth : layout.inspectorWidth;
  const next = clampWidth(zone, current + delta, viewport, layout);
  return zone === "rail" ? { ...layout, railWidth: next } : { ...layout, inspectorWidth: next };
}

/** Reset one zone, leaving the other alone. */
export function resetZone(zone: Zone, layout: Layout): Layout {
  return zone === "rail"
    ? { ...layout, railWidth: RAIL_DEFAULT }
    : { ...layout, inspectorWidth: INSPECTOR_DEFAULT };
}

export function reset(): Layout {
  return { ...DEFAULTS };
}

/** Total: any input at all produces a usable layout. A stored preference must never break the shell. */
export function parse(raw: string | null | undefined, viewport: number): Layout {
  if (!raw) return reset();
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return reset();
  }
  if (!data || typeof data !== "object" || Array.isArray(data)) return reset();
  const d = data as Record<string, unknown>;

  // Versioned on purpose: a future format is not this code's business, so it falls back whole.
  if (d.version !== undefined && d.version !== 1) return reset();

  const num = (v: unknown, fallback: number) =>
    typeof v === "number" && Number.isFinite(v) ? v : fallback;
  const bool = (v: unknown, fallback: boolean) => (typeof v === "boolean" ? v : fallback);

  const candidate: Layout = {
    railWidth: num(d.railWidth, RAIL_DEFAULT),
    inspectorWidth: num(d.inspectorWidth, INSPECTOR_DEFAULT),
    railVisible: bool(d.railVisible, DEFAULTS.railVisible),
    inspectorVisible: bool(d.inspectorVisible, DEFAULTS.inspectorVisible),
    railTab: RAIL_TABS.includes(d.railTab as RailTab) ? (d.railTab as RailTab) : DEFAULTS.railTab,
  };
  // Widths are re-clamped against the window this session actually has (edge case B8).
  return {
    ...candidate,
    railWidth: clampWidth("rail", candidate.railWidth, viewport, candidate),
    inspectorWidth: clampWidth("inspector", candidate.inspectorWidth, viewport, candidate),
  };
}

/** Geometry and a tab name. Never a path, a user id or anything from the workspace (SH-B5). */
export function serialize(layout: Layout): string {
  return JSON.stringify({
    version: 1,
    railWidth: layout.railWidth,
    inspectorWidth: layout.inspectorWidth,
    railVisible: layout.railVisible,
    inspectorVisible: layout.inspectorVisible,
    railTab: layout.railTab,
  });
}

/** What the user sees in a separator's accessible value. */
export function describe(zone: Zone, layout: Layout): { label: string; value: number; min: number; max: number } {
  return {
    label: zone === "rail" ? "Resize the navigator" : "Resize the inspector",
    value: zone === "rail" ? layout.railWidth : layout.inspectorWidth,
    min: minWidth(zone),
    max: Number.POSITIVE_INFINITY,
  };
}
