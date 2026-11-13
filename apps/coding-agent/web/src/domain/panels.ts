/** What every panel is doing right now, as ONE pure function of the user's intent and the window.
 *
 * Spec 012. The shell keeps four pieces of state that mean "this panel is open": the persisted
 * visibility (`layout.*Visible`), and two session flags — `dockDrawer` and `drawer` — that only say
 * "the user asked for the OVERLAY form". The session flags are meaningful in exactly one placement
 * each. App.tsx read them anywhere, and that is how it drew a full-window, invisible scrim over a
 * dock that was a plain COLUMN: any click on any panel closed the dock, and the wheel scrolled
 * nothing, because the scrim — not the panel — was under the pointer.
 *
 * So the rule of this module: **a flag is only read through `resolvePanels`**, which ignores it when
 * its panel is not an overlay. A stale flag can then be wrong about the past, never about the screen.
 *
 * The placements are the states of the diagrams in specs/012-panel-interaction/README.md.
 */
import {
  DOCK_FOCUS_MIN, modeFor, takesColumn, type Layout,
} from "./layout";

/** hidden: not drawn · column: a grid track · focus: a column in a window too narrow for the rail
 *  (the rail yields) · drawer: a fixed overlay above the work. */
export type DockPlacement = "hidden" | "column" | "focus" | "drawer";
export type RailPlacement = "hidden" | "column" | "drawer";

/** Which overlay owns the click-away layer, if any. `rail` dims the work; `dock` is transparent. */
export type ScrimKind = "none" | "rail" | "dock";

export interface PanelInput {
  layout: Layout;
  viewport: number;
  /** "The user asked for the dock's overlay form". Meaningless unless the dock cannot be a column. */
  dockDrawer: boolean;
  /** "The user asked for the navigator's overlay form". Meaningless while the navigator is a column. */
  railDrawer: boolean;
}

export interface PanelState {
  dock: DockPlacement;
  rail: RailPlacement;
  scrim: ScrimKind;
  /** Is the dock a fixed overlay (the only form that has a scrim and that Escape may dismiss)? */
  dockOverlay: boolean;
  /** Is the navigator a fixed overlay? */
  railOverlay: boolean;
  /** The topmost transient panel Escape would dismiss, in the order a user perceives them. */
  escape: "dock" | "rail" | "none";
}

export function resolvePanels(i: PanelInput): PanelState {
  const { layout, viewport } = i;
  const narrow = modeFor(viewport) === "narrow";

  // -- the dock ---------------------------------------------------------------------------
  // `takesColumn` already includes `assistantVisible`, so a hidden dock can never be a column.
  const dockColumn = takesColumn("assistant", layout, viewport);
  const dockWantsOverlay = layout.assistantVisible && !dockColumn;
  const dockOpenAsOverlay = dockWantsOverlay && i.dockDrawer;
  const dock: DockPlacement = dockColumn ? "column"
    : !dockOpenAsOverlay ? "hidden"
      : viewport >= DOCK_FOCUS_MIN ? "focus" : "drawer";

  // -- the navigator ----------------------------------------------------------------------
  const focusDock = dock === "focus";
  const railAsColumn = layout.railVisible && !narrow && !focusDock;
  const railAsDrawer = layout.railVisible && (narrow || focusDock) && i.railDrawer;
  const rail: RailPlacement = railAsColumn ? "column" : railAsDrawer ? "drawer" : "hidden";

  const dockOverlay = dock === "drawer";
  const railOverlay = rail === "drawer";
  return {
    dock, rail, dockOverlay, railOverlay,
    // The navigator drawer is modal (it dims and takes the click); the dock overlay is a sibling that
    // only offers click-away. Both exist only while their overlay is actually drawn.
    scrim: railOverlay ? "rail" : dockOverlay ? "dock" : "none",
    escape: dockOverlay ? "dock" : railOverlay ? "rail" : "none",
  };
}
