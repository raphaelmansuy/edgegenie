/** Put focus back where it was when a dialog closes. One hook, five call sites.
 *
 * Focus is the keyboard's cursor, so losing it loses the keyboard (`KB-1`, principle P1). The bug this
 * replaces was in every dialog at once and invisible in review: each dialog focused its own first
 * field on open, and none of them remembered what had focus before, so Escape dropped focus onto
 * `<body>` and the next Tab started again at the top of the page.
 *
 * The contract, in order:
 *   1. restore the element that had focus when the dialog opened, if it is still usable;
 *   2. otherwise the caller's `fallback` (the next tab, the composer, the centre pane);
 *   3. otherwise the last resort: `main`, then the body's first focusable element.
 *
 * "Usable" is stricter than `isConnected`: an element that has been hidden (a chip below 1100 px) is
 * still connected but cannot take focus, and focusing it silently does nothing — the same failure with
 * an extra step. So it must also be visible and not disabled (`E-37`).
 */
import { useLayoutEffect, useRef } from "react";

/** Can this element actually receive focus right now? */
export function isFocusable(el: Element | null): el is HTMLElement {
  if (!el || !(el instanceof HTMLElement)) return false;
  if (!el.isConnected) return false;
  if (el.hasAttribute("disabled")) return false;
  // Computed style, not `offsetParent`: a hidden element is still connected, and `offsetParent` is
  // null for every element in a headless DOM, so using it would reject everything outside a browser.
  const cs = getComputedStyle(el);
  if (cs.display === "none" || cs.visibility === "hidden") return false;
  // `checkVisibility` (where available) also catches `content-visibility: hidden` and a collapsed parent.
  if (typeof el.checkVisibility === "function" && !el.checkVisibility({ checkVisibilityCSS: true })) return false;
  return el.tabIndex >= -1;
}

/** The named successors, in order. Never `<body>`: a named region means the next Tab continues inside
 *  it, which is the whole point. */
export function successor(): HTMLElement | null {
  const candidates = [
    document.querySelector<HTMLElement>("[role=tab][aria-selected=true]"),
    document.querySelector<HTMLElement>(".composer textarea"),
    document.querySelector<HTMLElement>("main"),
    document.querySelector<HTMLElement>("#doc-panel"),
  ];
  for (const el of candidates) {
    if (!isFocusable(el)) continue;
    return el;
  }
  return null;
}

export function useReturnFocus(
  open: boolean | "mount" = "mount",
  opts?: { fallback?: () => HTMLElement | null; restore?: boolean },
): void {
  /** Captured at open, not at close: by close the user may have focused something inside the dialog. */
  const opener = useRef<HTMLElement | null>(null);
  const wasOpen = useRef(false);
  const restore = opts?.restore ?? true;
  const fallback = useRef(opts?.fallback);
  fallback.current = opts?.fallback;

  const record = () => {
    const active = document.activeElement;
    opener.current = active instanceof HTMLElement && active !== document.body ? active : null;
    wasOpen.current = true;
  };

  const give = () => {
    if (!wasOpen.current) return;
    wasOpen.current = false;
    const back = opener.current;
    opener.current = null;
    if (!restore) return;
    // Let React finish removing the dialog before moving focus: focusing during the same commit can be
    // undone by the removal's own cleanup (measured: focus landed on body with no error).
    window.requestAnimationFrame(() => {
      const target = isFocusable(back) ? back : fallback.current?.() ?? successor();
      target?.focus();
    });
  };

  /* Two shapes, one contract.
   *
   * Most of this app's dialogs are **conditionally rendered**: they mount to open and unmount to close.
   * For those, `open` is `"mount"` and the restore belongs in the unmount cleanup — a boolean prop
   * that is always `true` (which is what the first version of this hook was given) records on mount
   * and then has no close to observe, so focus was never returned at all. A dialog that stays mounted
   * and toggles can pass its `open` prop and gets the same behaviour.
   */
  /* A LAYOUT effect, not a passive one: children's effects run before the parent's, so a dialog's own
     "focus my first field" effect would run first and the recorded opener would be the dialog's own
     input. A layout effect runs before every passive effect in the tree, whatever the component
     order — measured: the passive version recorded `input.palette-input` instead of the button. */
  useLayoutEffect(() => {
    if (open === "mount") { record(); return give; }
    if (open) { record(); return; }
    give();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);
}
