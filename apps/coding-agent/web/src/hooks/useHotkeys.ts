/** One global keydown listener for the whole app. It dispatches; `resolve` decides.
 *
 * Registered once on the window: the alternative (a listener per component) makes shortcuts fight
 * each other and makes "why did my key do nothing" impossible to answer. A handler returning false
 * means it did not consume the key, so the browser default still runs.
 *
 * Since 007 the *arbitration* is not here (`KB-2`, `[D3]`). This hook asks `resolve()` — a pure
 * function over the key and the context — who owns the press, then calls that id's handler. So a
 * chord cannot have two owners, and the precedence is testable without a DOM.
 */
import { useEffect } from "react";
import { comboOf, isTyping, resolve, type KeyContext } from "../domain/keys";

export type Handlers = Record<string, () => boolean | void>;

/** What only the app knows: whether a dialog is open, whether a cell has focus. Read live, so the
 *  listener never needs re-registering when they change. */
export interface HotkeyContext {
  dialogOpen: () => boolean;
  inCell: () => boolean;
  running: () => boolean;
}

const DEFAULT_CONTEXT: HotkeyContext = {
  dialogOpen: () => Boolean(document.querySelector('[role="dialog"][aria-modal="true"]')),
  inCell: () => Boolean(document.activeElement?.closest?.(".cell-block")),
  running: () => false,
};

export function useHotkeys(handlers: Handlers, context: HotkeyContext = DEFAULT_CONTEXT): void {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const combo = comboOf(e);          // the same definition the registry and the sheet use
      const ctx: KeyContext = {
        // `isTyping` is an input to the decision, not a second filter in front of it.
        typing: isTyping(e.target, combo.includes("+")),
        dialog: context.dialogOpen(),
        cell: context.inCell(),
        running: context.running(),
      };
      const resolved = resolve(e, ctx);
      if (!resolved) return;
      // Escape is always handled by whoever is listening (a dialog's own keydown, or the shell's
      // ordered `escapeTarget`); it must never fall through to a browser action that hides the page.
      const handler = handlers[resolved.shortcut.id];
      if (!handler) return;
      if (handler() !== false) e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [handlers, context]);
}
