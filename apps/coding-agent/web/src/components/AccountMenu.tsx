/** Who you are, where you are, and the app's own settings: the avatar menu every workspace UI has.
 *
 * It answers the question a person has before trusting a tool with their workspace: "which account and
 * which workspace is this acting as?". Everything shown is already known to the app (`/api/me`); the
 * menu invents nothing and never shows a token.
 *
 * It also answers "which BUILD is this", which is the second question a person asks when something
 * looks wrong and they need to say what they were running. The version comes from the bundle and the
 * commit from the server (`/api/version`); both are links to the site, the source and the releases,
 * because the answer to "which version" is nearly always followed by "where is the changelog".
 */
import { useEffect, useRef, useState } from "react";
import { initials } from "../domain/sessions";
import { DOCS_URL, RELEASES_URL, SOURCE_URL, versionLabel, versionTitle, type BuildFacts } from "../domain/version";
import { CopyButton } from "./CopyButton";

export function AccountMenu({ user, host, folder, demo, onProviders, onKeys, build }: {
  user: string; host: string | null; folder: string; demo: boolean;
  onProviders: () => void; onKeys: () => void;
  /** Which build this page is, so the menu can state it. */
  build?: BuildFacts;
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
  const facts = build;

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
            {facts && (
              <>
                {/* "Which build am I running" is the first question after "which account", and it is
                    unanswerable from the page unless the page states it. The label links to the release
                    history, because that is what a version number is asking for. */}
                <dt>Version</dt>
                <dd>
                  <a className="ext-link-text version-link" href={RELEASES_URL} target="_blank"
                    rel="noopener noreferrer" title={versionTitle(facts)}>
                    {versionLabel(facts)}
                  </a>
                  {!facts.commit && <span className="version-note" title="A Workspace-folder deployment has no git checkout to report"> · no commit reported</span>}
                </dd>
              </>
            )}
          </dl>
          <button role="menuitem" className="account-item" onClick={act(onProviders)}>Providers and keys</button>
          <button role="menuitem" className="account-item" onClick={act(onKeys)}>Keyboard shortcuts</button>
          {/* The same two links the version row points at, named explicitly: a menu is where someone
              looks for "the docs" without knowing a version number leads there. */}
          <a role="menuitem" className="account-item" href={DOCS_URL} target="_blank" rel="noopener noreferrer"
            title="OpenGenie documentation, tour and install guide">Documentation ↗</a>
          <a role="menuitem" className="account-item" href={SOURCE_URL} target="_blank" rel="noopener noreferrer"
            title="Source code on GitHub">Source code ↗</a>
        </div>
      )}
    </div>
  );
}
