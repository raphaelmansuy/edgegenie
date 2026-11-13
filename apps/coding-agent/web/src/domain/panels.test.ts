import { describe, expect, it } from "vitest";
import { ASSISTANT_COLUMN_MIN, DEFAULTS, DOCK_FOCUS_MIN, type Layout } from "./layout";
import { resolvePanels, type PanelInput } from "./panels";

const layout = (extra: Partial<Layout> = {}): Layout => ({ ...DEFAULTS, ...extra });
const at = (viewport: number, extra: Omit<Partial<PanelInput>, "layout"> & { layout?: Partial<Layout> } = {}) => {
  const { layout: l, ...rest } = extra;
  return resolvePanels({ layout: layout(l), viewport, dockDrawer: false, railDrawer: false, ...rest });
};

describe("resolvePanels — the dock's placement is a function of intent and window, nothing else", () => {
  it("is a column wherever the arithmetic allows it, whatever the overlay flag says", () => {
    for (const flag of [false, true]) {
      expect(at(ASSISTANT_COLUMN_MIN, { dockDrawer: flag }).dock).toBe("column");
      expect(at(1500, { dockDrawer: flag }).dock).toBe("column");
    }
  });

  it("is hidden when the user hid it, even with the flag set", () => {
    expect(at(1500, { layout: { assistantVisible: false }, dockDrawer: true }).dock).toBe("hidden");
    expect(at(700, { layout: { assistantVisible: false }, dockDrawer: true }).dock).toBe("hidden");
  });

  it("is hidden below the column width until the user opens it (a drawer never opens itself)", () => {
    expect(at(1000).dock).toBe("hidden");
    expect(at(700).dock).toBe("hidden");
  });

  it("opens as the focus column between DOCK_FOCUS_MIN and the column width, and as a drawer below", () => {
    expect(at(DOCK_FOCUS_MIN, { dockDrawer: true }).dock).toBe("focus");
    expect(at(ASSISTANT_COLUMN_MIN - 1, { dockDrawer: true }).dock).toBe("focus");
    expect(at(DOCK_FOCUS_MIN - 1, { dockDrawer: true }).dock).toBe("drawer");
    expect(at(700, { dockDrawer: true }).dock).toBe("drawer");
  });
});

describe("resolvePanels — the click-away layer exists only while an overlay is drawn", () => {
  // The defect: ⌘J at a wide width set the overlay flag while the dock had a column. The layer then
  // covered the window, a click on any panel closed the dock, and the wheel scrolled nothing.
  it("never exists for a dock that has a column, however the flag got set", () => {
    const s = at(1500, { dockDrawer: true });
    expect(s.dock).toBe("column");
    expect(s.scrim).toBe("none");
    expect(s.escape).toBe("none");
  });

  it("never exists for the focus column either: it is a column", () => {
    const s = at(1000, { dockDrawer: true });
    expect(s.dock).toBe("focus");
    expect(s.scrim).toBe("none");
    expect(s.escape).toBe("none");
  });

  it("is transparent for the dock overlay and dims for the navigator overlay", () => {
    expect(at(700, { dockDrawer: true }).scrim).toBe("dock");
    expect(at(700, { railDrawer: true }).scrim).toBe("rail");
  });

  it("ignores a navigator flag left over from a window where the navigator was an overlay", () => {
    // 1500: the navigator is a column, so `railDrawer` is stale. It used to dim the whole window.
    const s = at(1500, { railDrawer: true });
    expect(s.rail).toBe("column");
    expect(s.scrim).toBe("none");
    // The same after the dock that made the navigator step aside is closed.
    const closed = at(1000, { railDrawer: true, dockDrawer: false });
    expect(closed.rail).toBe("column");
    expect(closed.scrim).toBe("none");
  });

  it("the navigator, being modal, owns the layer when both overlays are open", () => {
    const s = at(700, { dockDrawer: true, railDrawer: true });
    expect(s.scrim).toBe("rail");
    expect(s.escape).toBe("dock"); // Escape unwinds the topmost: the dock is above the navigator
  });
});

describe("resolvePanels — the navigator yields to the focus column and comes back as a drawer", () => {
  it("is a column when it fits, hidden when the focus dock needs the room", () => {
    expect(at(1000).rail).toBe("column");
    expect(at(1000, { dockDrawer: true }).rail).toBe("hidden");
  });
  it("is a drawer only on request, while it cannot be a column", () => {
    expect(at(1000, { dockDrawer: true, railDrawer: true }).rail).toBe("drawer");
    expect(at(700, { railDrawer: true }).rail).toBe("drawer");
    expect(at(700).rail).toBe("hidden");
  });
  it("is hidden when the user hid it", () => {
    expect(at(1500, { layout: { railVisible: false }, railDrawer: true }).rail).toBe("hidden");
  });
});

describe("resolvePanels — invariants over the whole space", () => {
  const widths = [320, 600, 700, 820, 821, 859, 860, 1000, 1135, 1136, 1180, 1181, 1300, 1476, 1600, 2400];
  const bools = [false, true];
  it("a scrim or an Escape target implies an overlay is drawn; a column implies neither", () => {
    for (const viewport of widths) for (const assistantVisible of bools) for (const railVisible of bools)
      for (const dockDrawer of bools) for (const railDrawer of bools) {
        const s = resolvePanels({ layout: layout({ assistantVisible, railVisible }), viewport, dockDrawer, railDrawer });
        const why = JSON.stringify({ viewport, assistantVisible, railVisible, dockDrawer, railDrawer, s });
        if (s.scrim === "dock") expect(s.dock, why).toBe("drawer");
        if (s.scrim === "rail") expect(s.rail, why).toBe("drawer");
        if (s.dock === "column" || s.dock === "focus") expect(s.escape === "dock", why).toBe(false);
        if (s.escape === "dock") expect(s.dock, why).toBe("drawer");
        if (s.escape === "rail") expect(s.rail, why).toBe("drawer");
        // Exactly one of the two overlays can own the layer, and none when neither is drawn.
        expect(s.scrim === "none", why).toBe(!s.dockOverlay && !s.railOverlay);
        // The flags change nothing when their panel is not an overlay.
        const quiet = resolvePanels({ layout: layout({ assistantVisible, railVisible }), viewport, dockDrawer: false, railDrawer: false });
        if (s.dock === "column") expect(quiet.dock, why).toBe("column");
        if (s.rail === "column") expect(quiet.rail === "column" || s.dock === "focus", why).toBe(true);
      }
  });
});
