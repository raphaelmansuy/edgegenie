/** The keyboard shortcut sheet: every shortcut, printed the way this platform prints keys.
 *
 * Discoverability is the difference between an app with shortcuts and an app people use shortcuts in.
 * Opened with ⌘/ and from the palette, so it can be found without knowing it exists.
 *
 * Grouped by **scope**, not by theme (007 `KB-6`): a shortcut list that hides "this only works in a
 * cell" teaches a wrong model of the app, and the reader finds out by pressing it and getting nothing.
 * The scopes come from the registry's `owner`, so the sheet cannot drift from the bindings.
 */
import { useEffect, useRef } from "react";
import { byScope, caps } from "../domain/keys";
import { useReturnFocus } from "../hooks/useReturnFocus";

export function ShortcutSheet({ onClose }: { onClose: () => void }) {
  const close = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    close.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  // KB-1: Escape must put focus back where the user left it, not on <body>.
  useReturnFocus();

  const scopes = byScope();

  return (
    <div className="scrim" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="sheet keys-sheet" role="dialog" aria-modal="true" aria-labelledby="keys-title">
        <header>
          <h2 id="keys-title">Keyboard shortcuts</h2>
          <p>Every chord below works where its column says. Modified chords also work from a text field.</p>
        </header>
        <div className="body keys-body">
          {scopes.map((s) => (
            <section key={s.scope} className="keys-group" aria-label={s.scope}>
              <h3>{s.scope}</h3>
              <dl>
                {s.items.map((k) => (
                  <div key={k.id} className="keys-row">
                    <dt>{k.label}</dt>
                    <dd>{caps(k.combo).map((cap, i) => <kbd key={i}>{cap}</kbd>)}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>
        <div className="actions">
          <button className="btn primary" ref={close} onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
