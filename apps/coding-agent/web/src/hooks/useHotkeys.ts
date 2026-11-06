/** One global keydown listener for the whole app. Keeps every shortcut in a single, testable place.
 *
 * Registered once on the window: the alternative (a listener per component) makes shortcuts fight
 * each other and makes "why did my key do nothing" impossible to answer. A handler returning false
 * means it did not consume the key, so the browser default still runs.
 */
import { useEffect } from "react";
import { comboOf, isTyping } from "../domain/keys";

export type Handlers = Record<string, () => boolean | void>;

export function useHotkeys(handlers: Handlers): void {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const combo = comboOf(e);          // the same definition the registry and the sheet use
      const handler = handlers[combo];
      if (!handler) return;
      // A bare key typed into a field is text, not a command. Modified combos still apply.
      if (isTyping(e.target, combo.includes("+"))) return;
      if (handler() !== false) e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [handlers]);
}
