/** The keyboard shortcut sheet: every shortcut, grouped, printed the way this platform prints keys.
 *
 * Discoverability is the difference between an app with shortcuts and an app people use shortcuts in.
 * Opened with ⌘/ and from the palette, so it can be found without knowing it exists.
 */
import { useEffect, useRef } from "react";
import { caps, grouped } from "../domain/keys";

export function ShortcutSheet({ onClose }: { onClose: () => void }) {
  const close = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    close.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="scrim" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="sheet keys-sheet" role="dialog" aria-modal="true" aria-labelledby="keys-title">
        <header>
          <h2 id="keys-title">Keyboard shortcuts</h2>
          <p>Everything here works anywhere, including from the message box.</p>
        </header>
        <div className="body keys-body">
          {grouped().map((g) => (
            <section key={g.group} className="keys-group">
              <h3>{g.group}</h3>
              <dl>
                {g.items.map((s) => (
                  <div key={s.id} className="keys-row">
                    <dt>{s.label}</dt>
                    <dd>{caps(s.combo).map((cap, i) => <kbd key={i}>{cap}</kbd>)}</dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>
        <div className="actions">
          <button className="btn" ref={close} onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  );
}
