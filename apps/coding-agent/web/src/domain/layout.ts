/** The shell's geometry: the only place that decides a column width.
 *
 * Pure, no React, no DOM. Every number a zone can take, every bound a drag must respect, and the
 * whole of "what survives a reload" lives here, so it can be tested without a browser and cannot
 * drift between the separator, the CSS and the persistence layer (specs/001-perfect-shell, SH-G3).
 *
 * The one rule this module exists to enforce: the centre column is never sacrificed. A panel may be
 * wide because the user dragged it, but never so wide that the work area drops below CENTRE_MIN.
 *
 * Spec 006 adds the **assistant** as a third zone. It is a new entry in the same model, not a second
 * layout system: `columns()` still produces the only grid string, and the same clamps apply.
 */

export type RailTab = "sessions" | "files" | "catalog" | "data";
export type Mode = "wide" | "mid" | "narrow";
export type Zone = "rail" | "inspector" | "assistant";

export interface Layout {
  railWidth: number;
  inspectorWidth: number;
  /** Spec 006 AD-9: the dock is resizable with the same rules as the other zones. */
  assistantWidth: number;
  railVisible: boolean;
  inspectorVisible: boolean;
  /** Spec 006 AD-2/AD-3: the dock's visibility is the user's, and `⌘J` toggles it. */
  assistantVisible: boolean;
  railTab: RailTab;
}

/** Bounds. One definition each: the separator, the CSS and the parser all read these. */
export const RAIL_MIN = 200;
export const RAIL_DEFAULT = 276;
export const INSPECTOR_MIN = 260;
export const INSPECTOR_MAX = 520;
export const INSPECTOR_DEFAULT = 340;
/** A conversation needs room for a code block and a two-line composer; below 320 it reflows per token. */
export const ASSISTANT_MIN = 320;
export const ASSISTANT_MAX = 560;
export const ASSISTANT_DEFAULT = 380;
/** Below this the centre column stops being usable for code. It wins every argument. */
export const CENTRE_MIN = 480;

/**
 * The widths at which the dock can take a column, derived rather than guessed.
 *
 *      rail + centre + dock            = 276 + 480 + 380 = 1136   (two columns)
 *      rail + centre + inspector + dock = 276 + 480 + 340 + 380 = 1476   (four columns)
 *
 * The first draft of spec 006 claimed three columns from 1180 px. At 1180 the arithmetic leaves the
 * centre 204 px, which is not a code column — so the numbers above replace the guess.
 *
 * The priority that follows is the point: **the conversation outranks the facts, and a column beats
 * an overlay.** Above 1136 px the dock takes a column and the editor shrinks by exactly that much.
 * Below it, it overlays. The inspector is the first thing to yield (it is facts a user consults), and
 * it only shares a column with the dock above 1476 px. A 420 px overlay covering the right third of
 * every cell — including its run control — is worse than a narrower editor, and the earlier "overlay
 * from 1180" rule did exactly that (found by the scorecard: a run button at x=1042 was covered).
 */
/* `gaps(3)` and `gaps(4)` are not decoration: the minimums are sums of column widths, and a grid with
   N tracks also spends (N−1) px on 1px separators. Without them the promise is off by exactly the
   number of panels, so at 1136 px — the width the comment below calls "the dock's minimum" — the
   centre measured 478 px, not CENTRE_MIN. Small, and still a broken promise at the one width where it
   is easiest to believe it holds. */
export const ASSISTANT_COLUMN_MIN = RAIL_DEFAULT + CENTRE_MIN + ASSISTANT_DEFAULT + 2;
export const ALL_FOUR_MIN = RAIL_DEFAULT + INSPECTOR_DEFAULT + ASSISTANT_DEFAULT + CENTRE_MIN + 3;
/**
 * FOCUS: the conversation beside the work, in a window too narrow for the rail as well.
 *
 *      centre + dock = 480 + 380 = 860
 *
 * Between 860 and 1136 px an opened assistant used to be an overlay that covered the right third of
 * the notebook — the very thing the user was asking about and watching change. Now it takes a column
 * and the navigator yields (it is a chooser: it comes back as a drawer when asked for). The notebook
 * stays fully visible and updates under the conversation. Below 860 px there is no room for both and
 * the dock remains an overlay.
 */
export const DOCK_FOCUS_MIN = CENTRE_MIN + ASSISTANT_DEFAULT;
export const canFocusDock = (viewport: number): boolean =>
  viewport >= DOCK_FOCUS_MIN && viewport < ASSISTANT_COLUMN_MIN;
/** A panel may never take more than this share of the window. */
export const MAX_SHARE = 0.4;
/** Steps for the keyboard, in px. Shift is the coarse step. */
export const KEY_STEP = 8;
export const KEY_STEP_COARSE = 64;

export const RAIL_TABS: readonly RailTab[] = ["sessions", "files", "catalog", "data"];

export const DEFAULTS: Layout = {
  railWidth: RAIL_DEFAULT,
  inspectorWidth: INSPECTOR_DEFAULT,
  assistantWidth: ASSISTANT_DEFAULT,
  railVisible: true,
  inspectorVisible: false,
  assistantVisible: true,
  railTab: "sessions",
};

export const STORAGE_KEY = "coding-agent:layout:v1";
/** v2 adds the assistant zone. A v1 blob is upgraded rather than discarded: it is still valid geometry. */
export const STORAGE_VERSION = 2;

/** wide: three columns · mid: the side panels are overlays · narrow: both are overlays. */
export function modeFor(viewport: number): Mode {
  if (!Number.isFinite(viewport) || viewport <= 0) return "wide";
  return viewport <= 820 ? "narrow" : viewport <= 1180 ? "mid" : "wide";
}

/** Does this zone take a grid column at this viewport? An overlay takes none.
 *
 * The priority is explicit: the rail, then the dock, then the inspector. The inspector is facts a
 * user consults; the dock is the conversation they are having. When only two fit, the dock keeps its
 * column and the inspector becomes the drawer it already is at `mid` (see ASSISTANT_COLUMN_MIN).
 */
export function takesColumn(zone: Zone, layout: Layout, viewport: number, focus = false): boolean {
  // Focus: the user opened the dock in a window with room for it and the work only.
  if (focus) return zone === "assistant";
  const mode = modeFor(viewport);
  if (zone === "rail") return mode !== "narrow" && layout.railVisible;
  // The dock takes a column as soon as the arithmetic allows it (1136 px), not only in `wide`:
  // a column is always better than an overlay, because an overlay covers the thing being worked on.
  if (zone === "assistant") return layout.assistantVisible && viewport >= ASSISTANT_COLUMN_MIN;
  // inspector: needs a reason to show, and either no dock competing for the room or enough width for
  // all four columns. It is the facts panel, so it yields first.
  const dockCompetes = layout.assistantVisible;
  const roomForAll = !dockCompetes || viewport >= ALL_FOUR_MIN;
  return mode === "wide" && layout.inspectorVisible && roomForAll;
}

/** Every column is separated by a 1px grid gap; the arithmetic that reserves CENTRE_MIN must count them
 *  or it is off by (columns − 1) px — which is exactly the kind of "why is it 477?" a reviewer finds. */
const GAP = 1;
const gaps = (columns: number): number => Math.max(0, columns - 1) * GAP;

const widthOf = (zone: Zone, layout: Layout): number =>
  zone === "rail" ? layout.railWidth : zone === "inspector" ? layout.inspectorWidth : layout.assistantWidth;

/** The widest a zone may be, given the other zones and the window. May be below the minimum in a tiny
 *  window; callers clamp to the minimum first and accept the overflow, since a 200 px panel in a 300 px
 *  window is the user's problem, not the arithmetic's. */
export function maxWidth(zone: Zone, layout: Layout, viewport: number): number {
  const others = (["rail", "inspector", "assistant"] as Zone[])
    .filter((z) => z !== zone && takesColumn(z, layout, viewport))
    .reduce((sum, z) => sum + widthOf(z, layout), 0);
  const share = Math.floor(viewport * MAX_SHARE);
  // No cap for the rail: it may use everything the share allows. The side panels have their own.
  const cap = zone === "inspector" ? INSPECTOR_MAX : zone === "assistant" ? ASSISTANT_MAX : Number.POSITIVE_INFINITY;
  return Math.max(minWidth(zone), Math.min(share, viewport - others - CENTRE_MIN, cap));
}

export function minWidth(zone: Zone): number {
  return zone === "rail" ? RAIL_MIN : zone === "inspector" ? INSPECTOR_MIN : ASSISTANT_MIN;
}

export function defaultWidth(zone: Zone): number {
  return zone === "rail" ? RAIL_DEFAULT : zone === "inspector" ? INSPECTOR_DEFAULT : ASSISTANT_DEFAULT;
}

/** A width the zone is allowed to have. Integral, because a half pixel renders as a blurry divider. */
export function clampWidth(zone: Zone, want: number, viewport: number, layout: Layout = DEFAULTS): number {
  const lo = minWidth(zone);
  const hi = maxWidth(zone, layout, viewport);
  const w = Number.isFinite(want) ? Math.round(want) : defaultWidth(zone);
  return Math.max(lo, Math.min(w, Math.max(lo, hi)));
}

/** The value for grid-template-columns. This function is the only producer of that string. */
export function columns(layout: Layout, viewport: number, focus = false, inspectorDrawer = false): string {
  const parts: string[] = [];
  if (takesColumn("rail", layout, viewport, focus)) {
    parts.push(`${clampWidth("rail", layout.railWidth, viewport, layout)}px`);
  }
  parts.push("minmax(0, 1fr)");
  // Order matters: the inspector sits between the work area and the assistant, so the assistant is
  // the right-most column and its separator is the outermost edge — visually stable across a resize.
  if (takesColumn("inspector", layout, viewport, focus)) {
    parts.push(`${clampWidth("inspector", layout.inspectorWidth, viewport, layout)}px`);
  }
  if (takesColumn("assistant", layout, viewport, focus)) {
    parts.push(`${clampWidth("assistant", layout.assistantWidth, viewport, layout)}px`);
  }
  /* The inspector's drawer is the last column, outside the dock: it is the right-most surface, exactly
     as it is when it has a column of its own.
   *
   * It YIELDS to `CENTRE_MIN` like every other zone. As a fixed-width column it took 340 px from a
   * window that had already given 276 to the rail and 380 to the dock, leaving the centre 477 px —
   * below the one number this module exists to defend (measured: 1440 → main 477).
   *
   * The width comes from `drawerWidth`, which returns `null` when the drawer cannot be a column at
   * all. That null is the whole point: with a floor of its own minimum, the drawer kept a 260 px
   * track in a 1180 px window and crushed the centre to 261 px — worse than the bug this replaced,
   * and it rendered the notebook's cell toolbars on top of each other (measured: `cell-bar` 221 px
   * of content in a 139 px box). A panel never wins against the work area; when it cannot fit it is
   * an overlay instead, which is the same panel drawn over the work rather than beside it. */
  /* Only when the inspector is NOT already a column. Asking for both is a caller error, and this is a
     total function: a panel that is already on screen does not also get a drawer track, because that
     pushed the track count past the child count again — the exact failure that wrapped the dock. */
  if (inspectorDrawer && !takesColumn("inspector", layout, viewport, focus)) {
    const w = drawerWidth(layout, viewport);
    if (w !== null) parts.push(`${w}px`);
  }
  return parts.join(" ");
}

/** The inspector drawer's width as a grid track, or `null` when it must be a fixed overlay instead.
 *
 *  One function, two callers: `columns()` decides the track from it, and App decides `below-bar` (the
 *  grid-child class) from it. They cannot disagree, which matters because they once did — the track
 *  count and the child count diverged and the dock silently wrapped to a second grid row.
 *
 *  It costs a track AND a gap, so both are subtracted before `CENTRE_MIN` is reserved. */
export function drawerWidth(layout: Layout, viewport: number): number | null {
  const others = (["rail", "assistant"] as Zone[]).filter((z) => takesColumn(z, layout, viewport));
  const used = others.reduce((sum, z) => sum + clampWidth(z, widthOf(z, layout), viewport, layout), 0);
  const room = viewport - used - gaps(others.length + 2) - CENTRE_MIN;
  if (room < INSPECTOR_MIN) return null;
  return Math.min(clampWidth("inspector", layout.inspectorWidth, viewport, layout), room);
}

/** Give one zone an absolute width, clamped. Total over `Zone`: every zone writes its OWN field.
 *
 *  This replaces a ternary in the hook that knew two zones (`rail ? railWidth : inspectorWidth`), so
 *  the assistant's separator silently resized the inspector — a panel that is hidden at the widths
 *  where the dock matters. Dragging the right panel therefore did nothing visible. The lookup table
 *  below cannot fall through to the wrong field, and a test walks every zone. */
export function withWidth(zone: Zone, layout: Layout, want: number, viewport: number): Layout {
  const next = clampWidth(zone, want, viewport, layout);
  return { ...layout, [WIDTH_FIELD[zone]]: next };
}

const WIDTH_FIELD = {
  rail: "railWidth", inspector: "inspectorWidth", assistant: "assistantWidth",
} as const satisfies Record<Zone, keyof Layout>;

/** A drag or a keypress. `delta` is px: positive widens the zone. */
export function resizeBy(zone: Zone, layout: Layout, viewport: number, delta: number): Layout {
  return withWidth(zone, layout, widthOf(zone, layout) + delta, viewport);
}

/** After the window changes: every zone is brought back inside the bounds of the new window. */
export function reclamp(layout: Layout, viewport: number): Layout {
  return (["rail", "inspector", "assistant"] as Zone[])
    .reduce((l, z) => withWidth(z, l, widthOf(z, l), viewport), layout);
}

/** Reset one zone, leaving the others alone. */
export function resetZone(zone: Zone, layout: Layout): Layout {
  if (zone === "rail") return { ...layout, railWidth: RAIL_DEFAULT };
  if (zone === "inspector") return { ...layout, inspectorWidth: INSPECTOR_DEFAULT };
  return { ...layout, assistantWidth: ASSISTANT_DEFAULT };
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

  // Versioned on purpose. v1 is the geometry before the assistant zone existed: its widths are still
  // meaningful, so it is upgraded rather than dropped; anything else falls back whole.
  if (d.version !== undefined && d.version !== 1 && d.version !== STORAGE_VERSION) return reset();

  const num = (v: unknown, fallback: number) =>
    typeof v === "number" && Number.isFinite(v) ? v : fallback;
  const bool = (v: unknown, fallback: boolean) => (typeof v === "boolean" ? v : fallback);

  const candidate: Layout = {
    railWidth: num(d.railWidth, RAIL_DEFAULT),
    inspectorWidth: num(d.inspectorWidth, INSPECTOR_DEFAULT),
    assistantWidth: num(d.assistantWidth, ASSISTANT_DEFAULT),
    railVisible: bool(d.railVisible, DEFAULTS.railVisible),
    inspectorVisible: bool(d.inspectorVisible, DEFAULTS.inspectorVisible),
    // A v1 blob has no opinion about the dock, and the dock's default is "open": it is the surface
    // this whole spec is about, and starting closed would hide it from every existing user.
    assistantVisible: bool(d.assistantVisible, DEFAULTS.assistantVisible),
    railTab: RAIL_TABS.includes(d.railTab as RailTab) ? (d.railTab as RailTab) : DEFAULTS.railTab,
  };
  // Widths are re-clamped against the window this session actually has (edge case B8).
  return {
    ...candidate,
    railWidth: clampWidth("rail", candidate.railWidth, viewport, candidate),
    inspectorWidth: clampWidth("inspector", candidate.inspectorWidth, viewport, candidate),
    assistantWidth: clampWidth("assistant", candidate.assistantWidth, viewport, candidate),
  };
}

/** Geometry and a tab name. Never a path, a user id or anything from the workspace (SH-B5). */
export function serialize(layout: Layout): string {
  return JSON.stringify({
    version: STORAGE_VERSION,
    railWidth: layout.railWidth,
    inspectorWidth: layout.inspectorWidth,
    assistantWidth: layout.assistantWidth,
    railVisible: layout.railVisible,
    inspectorVisible: layout.inspectorVisible,
    assistantVisible: layout.assistantVisible,
    railTab: layout.railTab,
  });
}

const ZONE_LABEL: Record<Zone, string> = {
  rail: "Resize the navigator",
  inspector: "Resize the inspector",
  assistant: "Resize the assistant",
};

/** What the user sees in a separator's accessible value. */
export function describe(zone: Zone, layout: Layout): { label: string; value: number; min: number; max: number } {
  return {
    label: ZONE_LABEL[zone],
    value: widthOf(zone, layout),
    min: minWidth(zone),
    max: Number.POSITIVE_INFINITY,
  };
}

/** What a separator tells assistive tech, with the bound that applies in THIS window. */
export function bounds(zone: Zone, layout: Layout, viewport: number): { min: number; max: number } {
  return { min: minWidth(zone), max: maxWidth(zone, layout, viewport) };
}
