/** Copy text to the clipboard. Resolves to whether it worked, and never throws.
 *
 * `navigator.clipboard` is absent on an insecure origin and rejects without a user gesture or when the
 * permission is denied (an iframe, a locked-down browser). A copy button that silently does nothing is
 * worse than none, so there is a fallback through a selected `<textarea>`, and the caller is told.
 */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) { await navigator.clipboard.writeText(text); return true; }
  } catch { /* fall through to the legacy path */ }
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.cssText = "position:fixed;top:0;left:0;opacity:0;pointer-events:none";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    ta.remove();
    return ok;
  } catch { return false; }
}
