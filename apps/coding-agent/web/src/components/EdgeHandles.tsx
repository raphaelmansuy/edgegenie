/** The edge handles: a way back to a hidden panel, where the panel would be.
 *
 * The top bar has had toggles for all three zones since 006, and the audit for `ZN-7` proved they
 * work — hidden, every panel could be restored with them. So why does this component exist?
 *
 * Because a control that exists is not a control that is **found**. In the report that opened this
 * work, the user had hidden the right panel, was looking at the right edge of the window, and saw
 * nothing there. The one control that would have helped was 900 px away in a row of eleven unlabelled
 * icon buttons, three of which look almost identical. That is a discoverability failure, not a missing
 * control, and the fix is the same one every editor converged on: **put the handle on the edge the
 * panel slides out from**.
 *
 * Design rules this follows:
 *  - it appears only when its panel is hidden, so it never competes with the panel itself;
 *  - it is a real button with a name, a tooltip and the chord, so it is reachable by keyboard and
 *    screen reader and teaches the shortcut while it is used;
 *  - it sits in the centre pane's own padding, absolutely positioned, so it costs no layout;
 *  - three of them stack when all three are hidden, in the reading order the panels appear.
 */
import { PanelLeft, PanelRight, Sparkle } from "./Icons";
import { display } from "../domain/keys";

export interface EdgeHandle {
  id: string;
  /** What the button says out loud. */
  label: string;
  /** The chord, shown in the tooltip. */
  combo: string;
  onOpen: () => void;
  /** Which edge the panel comes from. Defaults to the right. */
  side?: "left" | "right";
}

/** The default set: whatever is hidden, with the chord each one answers to. */
export function handlesFor(p: {
  dockHidden: boolean; inspectorHidden: boolean; railHidden: boolean;
  onDock: () => void; onInspector: () => void; onRail: () => void;
}): EdgeHandle[] {
  /* Right edge, in the order the panels sit there; then the left edge. The set is derived from what is
     hidden, so a new zone cannot forget its handle — it fails the panels e2e instead. */
  const out: EdgeHandle[] = [];
  /* The name must CONTAIN the word drawn on the handle (Context / Chat / Files), or a voice-control
     user reading the button aloud cannot activate it — WCAG 2.5.3, Label in Name. It must also not
     repeat the top bar toggle's name exactly: two buttons called "Show the inspector" gave a screen
     reader two identical stops and made `getByRole` ambiguous, which surfaced as a crashing audit. */
  if (p.inspectorHidden) {
    out.push({ id: "inspector", label: "Show the Context panel", combo: "mod+i", onOpen: p.onInspector });
  }
  if (p.dockHidden) {
    out.push({ id: "dock", label: "Show the Chat panel", combo: "mod+j", onOpen: p.onDock });
  }
  if (p.railHidden) {
    out.push({ id: "rail", label: "Show the Files panel", combo: "mod+b", onOpen: p.onRail, side: "left" });
  }
  return out;
}

export function EdgeHandles({ handles }: { handles: EdgeHandle[] }) {
  if (handles.length === 0) return null;
  const right = handles.filter((h) => h.side !== "left");
  const left = handles.filter((h) => h.side === "left");
  /* No chevron: inside a `writing-mode: vertical-rl` label it rotates with the text and points
     downwards, which reads as "collapse" — measured in the 3x crop. The icon plus the word carry the
     meaning, and the word is what a user actually reads. */
  const one = (h: EdgeHandle) => (
    <button
      key={h.id}
      type="button"
      className={`edge-handle is-${h.side ?? "right"}`}
      onClick={h.onOpen}
      aria-label={h.label}
      title={`${h.label} (${display(h.combo)})`}
    >
      {/* The glyph says which panel; the arrow says it comes from this edge; the word says what it is
          for. A vertical word reads without turning the head, and it is what turns an anonymous icon
          into a labelled control in the exact place the user is looking. */}
      {h.id === "inspector" ? <PanelRight size={13} /> : h.id === "rail" ? <PanelLeft size={13} /> : <Sparkle size={13} />}
      <span className="edge-handle-word" aria-hidden>{h.id === "inspector" ? "Context" : h.id === "rail" ? "Files" : "Chat"}</span>
    </button>
  );
  return (
    <>
      {left.length > 0 && (
        <div className="edge-handles is-left" role="group" aria-label="Hidden left panels">{left.map(one)}</div>
      )}
      {right.length > 0 && (
        <div className="edge-handles" role="group" aria-label="Hidden panels">{right.map(one)}</div>
      )}
    </>
  );
}
