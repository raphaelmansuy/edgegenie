/** The layout menu: hide, show and reset the shell's zones, without the keyboard.
 *
 * A memoised, self-contained component on purpose. It sits in the top bar, which re-renders on every
 * streamed token of a turn; if this were inline JSX, React would replace the button between the
 * user's mousedown and their click, and the menu would swallow the press. (Seen on the deployed app:
 * Reset appeared to do nothing.) Keeping it here means a streaming turn cannot disturb it.
 */
import { memo } from "react";
import { display } from "../domain/keys";
import { Check, LayoutGrid } from "./Icons";

interface Props {
  open: boolean;
  onOpen: () => void;
  railVisible: boolean;
  /** Whether the CONVERSATION is on screen. It was missing from this menu entirely, so a user who
   *  hid the assistant and reached for the layout menu — the obvious place — found no way back. */
  dockVisible: boolean;
  inspectorVisible: boolean;
  /** Kept as a prop for callers that may need to say why, but no longer gates the item: the
   *  inspector always has something to show (the fence, the tools, the audit log), and a disabled
   *  control with no alternative is how a panel becomes unrecoverable. */
  inspectorAvailable: boolean;
  onToggleRail: () => void;
  onToggleDock: () => void;
  onToggleInspector: () => void;
  onReset: () => void;
  onKeys: () => void;
}

export const LayoutMenu = memo(function LayoutMenu({
  open, onOpen, railVisible, dockVisible, inspectorVisible, inspectorAvailable,
  onToggleRail, onToggleDock, onToggleInspector, onReset, onKeys,
}: Props) {
  return (
    <div className="menu-wrap">
      <button className="btn ghost" aria-haspopup="menu" aria-expanded={open}
        onClick={onOpen} aria-label="Layout and panels" title="Layout and panels">
        <LayoutGrid size={16} />
      </button>
      {open && (
        <div className="menu" role="menu" aria-label="Layout">
          <button role="menuitemcheckbox" aria-checked={railVisible} onClick={onToggleRail}>
            <span className="menu-tick" aria-hidden>{railVisible && <Check size={13} />}</span> Navigator
            <kbd>{display("mod+b")}</kbd>
          </button>
          <button role="menuitemcheckbox" aria-checked={dockVisible} onClick={onToggleDock}>
            <span className="menu-tick" aria-hidden>{dockVisible && <Check size={13} />}</span> Assistant
            <kbd>{display("mod+j")}</kbd>
          </button>
          {/* The tick must describe what is on screen, not what was last asked for. A session-less
              window saves inspector:true by default, so ticking it while rendering nothing is a lie. */}
          <button role="menuitemcheckbox" aria-checked={inspectorVisible} onClick={onToggleInspector}
            disabled={!inspectorAvailable}
            title={inspectorAvailable ? undefined : "The inspector appears once a session is open"}>
            <span className="menu-tick" aria-hidden>{inspectorVisible && <Check size={13} />}</span> Inspector
            <kbd>{display("mod+i")}</kbd>
          </button>
          <hr />
          <button role="menuitem" onClick={onReset}>
            <span aria-hidden /> Reset layout
          </button>
          <button role="menuitem" onClick={onKeys}>
            <span aria-hidden /> Keyboard shortcuts…
          </button>
        </div>
      )}
    </div>
  );
});
