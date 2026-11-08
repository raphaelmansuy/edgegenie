/** Skip links: the index of the shell, for the keyboard.
 *
 * The shell has four regions, and a keyboard user's first Tab used to land on the model chip at the
 * far right of the top bar — with forty Tab presses between there and the code (measured; 007
 * `ZN-5`). A skip link is the browser-native answer and works everywhere, unlike landmark navigation
 * keys, which browsers do not expose consistently (`[D4]`).
 *
 * Two rules make it work rather than merely exist:
 *
 *  1. it **moves focus**, not just the scroll position — so the next Tab continues *inside* the
 *     region rather than from the top of the page again;
 *  2. it is **visible when focused**: `transform` at rest, in flow on `:focus-visible`, in the accent
 *     pairing (`--on-accent` on `--blue-600`) so it cannot be missed in the one moment it matters.
 *
 * The targets carry `tabIndex={-1}`: focusable programmatically, absent from the Tab ring, so the
 * ring itself does not grow.
 */
const TARGETS = [
  { id: "doc-panel", label: "Skip to the work" },
  { id: "dock", label: "Skip to the conversation" },
] as const;

/** Move focus to a region by id. Shared by both links so the behaviour cannot differ between them. */
export function focusRegion(id: string): void {
  const el = document.getElementById(id);
  if (!el) return;
  if (el.tabIndex < 0 && !el.hasAttribute("tabindex")) el.setAttribute("tabindex", "-1");
  el.focus({ preventScroll: true });
  // `preventScroll` keeps the page still — the region is already on screen (the page never scrolls).
  // A region that is scrolled internally scrolls itself when its focused child is revealed.
}

export function SkipLinks({ targets = TARGETS }: { targets?: readonly { id: string; label: string }[] }) {
  return (
    <div className="skip-links">
      {targets.map((t) => (
        <a
          key={t.id}
          className="skip-link"
          href={`#${t.id}`}
          onClick={(e) => {
            // A skip link is a focus move, not a navigation: without this the hash changes and the
            // router treats it as a new route.
            e.preventDefault();
            focusRegion(t.id);
          }}
        >
          {t.label}
        </a>
      ))}
    </div>
  );
}
