/** Who you are, where you are, and the app's own settings: the avatar menu every workspace UI has.
 *
 * It answers the question a person has before trusting a tool with their workspace: "which account and
 * which workspace is this acting as?". Everything shown is already known to the app (`/api/me`); the
 * menu invents nothing and never shows a token.
 */
import { useEffect, useRef, useState } from "react";
import { initials } from "../domain/sessions";
import { CopyButton } from "./CopyButton";

export function AccountMenu({ user, host, folder, demo, onProviders, onKeys }: {
  user: string; host: string | null; folder: string; demo: boolean; onProviders: () => void; onKeys: () => void;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const down = (e: MouseEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(false); trigger.current?.focus(); } };
    window.addEventListener("mousedown", down);
    window.addEventListener("keydown", key);
    return () => { window.removeEventListener("mousedown", down); window.removeEventListener("keydown", key); };
  }, [open]);

  const name = user || "Not signed in";
  const hostName = host ? host.replace(/^https?:\/\//, "") : "";
  const act = (f: () => void) => () => { setOpen(false); f(); };

  return (
    <div className="account" ref={root}>
      <button ref={trigger} type="button" className="avatar-btn" aria-haspopup="menu" aria-expanded={open}
        aria-label={`Account: ${name}`} title={name} onClick={() => setOpen((o) => !o)}>
        {initials(user)}
      </button>
      {open && (
        <div className="account-pop" role="menu" aria-label="Account">
          <div className="account-id">
            <span className="avatar-btn lg" aria-hidden>{initials(user)}</span>
            <div>
              <div className="account-name">{name}</div>
              {demo && <span className="pill demo">demo mode · no workspace</span>}
            </div>
          </div>
          <dl className="account-facts">
            <dt>Workspace</dt>
            <dd>{hostName ? <a href={host ?? undefined} target="_blank" rel="noopener noreferrer" className="ext-link-text">{hostName} ↗</a> : "not connected"}</dd>
            <dt>Working folder</dt>
            <dd>{folder ? <><code>{folder}</code> <CopyButton text={folder} label="Copy" className="copy-btn quiet" title="Copy the path" /></> : "—"}</dd>
          </dl>
          <button role="menuitem" className="account-item" onClick={act(onProviders)}>Providers and keys</button>
          <button role="menuitem" className="account-item" onClick={act(onKeys)}>Keyboard shortcuts</button>
        </div>
      )}
    </div>
  );
}
