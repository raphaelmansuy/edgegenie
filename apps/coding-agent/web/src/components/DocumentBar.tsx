/** The document bar: one row that carries identity, the fence, the ask menu and Save.
 *
 * This replaces three stacked blocks — a 128 px header, a 40 px editor bar, and a separate action
 * row — which together spent 168 px of a 900 px viewport before any code was visible. Measured:
 * the whole app spent 234 px of chrome, 26% of the window. Databricks spends about 150.
 *
 * The merge is not only about height. It fixes a control-choice problem: `Explain`, `Fix errors`,
 * `Document` and `Optimize` are four variations of *"ask the agent to do something to this file"*,
 * so they belong behind one `Ask ▾` control rather than competing with the file name for width.
 *
 * The fence stays in the bar, because WR-5 requires it to be visible **before** the first keystroke.
 */
import { useEffect, useRef, useState } from "react";
import { ACTIONS, ACTIONS_FOR, type Action, type Doc } from "../domain/docs";
import { Check, ChevronDown, Clock, Close, Lock, Refresh, Save as SaveIcon, Warning } from "./Icons";

export interface BarFence {
  label: string;
  tone: "ok" | "warn" | "off";
  reason: string;
}

interface Props {
  doc: Doc;
  /** Path segments for the breadcrumb, e.g. ["agent_scratch", "revenue_by_hour"]. */
  crumbs: string[];
  language?: string;
  fence: BarFence;
  readOnly: boolean;
  dirty: boolean;
  saving: boolean;
  busy: boolean;
  notice: { tone: "ok" | "warn" | "error"; text: string } | null;
  /** The full path, for the copy affordance and the title. */
  path: string;
  onReload: () => void;
  onSave: () => void;
  onAsk: (a: Action) => void;
  onAttach: () => void;
  onOpenInDatabricks: () => void;
}

export function DocumentBar({
  doc, crumbs, language, fence, readOnly, dirty, saving, busy, notice, path,
  onReload, onSave, onAsk, onAttach, onOpenInDatabricks,
}: Props) {
  const [menu, setMenu] = useState(false);
  const [copied, setCopied] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!menu) return;
    const down = (e: MouseEvent) => {
      if (!(e.target as HTMLElement)?.closest(".ask-wrap")) setMenu(false);
    };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") setMenu(false); };
    window.addEventListener("mousedown", down);
    window.addEventListener("keydown", key);
    return () => { window.removeEventListener("mousedown", down); window.removeEventListener("keydown", key); };
  }, [menu]);

  const Icon = readOnly ? Lock : fence.tone === "ok" ? Check : fence.tone === "warn" ? Warning : Lock;
  const actions = ACTIONS_FOR[doc.kind];

  return (
    <header className="doc-bar">
      {/* Identity: name, language, breadcrumb — the things you need to know where you are. */}
      <div className="doc-id">
        <span className="doc-name" title={path}>{doc.name}</span>
        {language && <span className="doc-lang">{language}</span>}
        <button className="doc-crumbs" title={`${path} — click to copy`}
          aria-label={`Copy the path ${path}`}
          onClick={() => {
            void navigator.clipboard?.writeText(path);
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1200);
          }}>
          {copied ? "copied" : crumbs.map((c, i) => (
            <span key={`${c}-${i}`} className="crumb">
              {i > 0 && <span className="crumb-sep" aria-hidden>/</span>}
              {c}
            </span>
          ))}
        </button>
      </div>

      <span className="doc-bar-spacer" />

      {notice && <span className={`doc-notice is-${notice.tone}`} role="status">{notice.text}</span>}

      {/* Fence: present before the first keystroke (WR-5), and never colour-only (UX-5). */}
      <span className={`fence-chip fence-${fence.tone}`} title={readOnly ? "this document is too large to save back safely" : fence.reason || "you can save here"}>
        <Icon size={13} />
        <span className="fence-text">{fence.label}</span>
      </span>

      <button className="icon-btn" aria-label="Reload this document" title="Reload from the server"
        onClick={onReload} disabled={busy}>
        <Refresh size={15} className={busy ? "spin" : ""} />
      </button>

      <button className="icon-btn" aria-label="Open in Databricks" title="Open in Databricks"
        onClick={onOpenInDatabricks}><span aria-hidden>↗</span></button>

      {/* Four prompts, one control. Each is "ask the agent about this file". */}
      <div className="ask-wrap" ref={wrap}>
        <button className="btn sm ask-btn" aria-haspopup="menu" aria-expanded={menu}
          onClick={() => setMenu((m) => !m)} title="Ask the agent to do something to this file">
          Ask <ChevronDown size={12} />
        </button>
        {menu && (
          <div className="menu ask-menu" role="menu" aria-label="Ask the agent">
            <button role="menuitem" onClick={() => { setMenu(false); onAttach(); }}>
              <span aria-hidden>＠</span> Add to chat
            </button>
            {actions.map((action) => (
              <button key={action} role="menuitem" onClick={() => { setMenu(false); onAsk(action); }}>
                <span aria-hidden />
                {ACTIONS[action].label}
              </button>
            ))}
          </div>
        )}
      </div>

      <button className="btn primary sm" onClick={onSave} disabled={readOnly || saving || !dirty}
        title={readOnly ? "this document cannot be saved" : "Save (⌘S)"}>
        {saving ? <Clock size={14} className="icon-spin" /> : <SaveIcon size={14} />}
        <span>Save</span>
      </button>
    </header>
  );
}

/** Split an absolute workspace path into readable crumbs, keeping the last two segments.
 *  A 90-character path is a fence value, not a location you can read at a glance. */
export function crumbsOf(path: string, keep = 2): string[] {
  const parts = path.split("/").filter(Boolean);
  return parts.slice(-keep);
}

/** A tiny dismiss control used by the banners this bar's callers render. */
export function Dismiss({ onClick }: { onClick: () => void }) {
  return (
    <button className="icon-btn" aria-label="Dismiss" onClick={onClick}><Close size={12} /></button>
  );
}
