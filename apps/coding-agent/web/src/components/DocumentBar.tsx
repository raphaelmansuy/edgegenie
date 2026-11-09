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
import { useEffect, useState } from "react";
import { ACTIONS, ACTIONS_FOR, type Action, type Doc } from "../domain/docs";
import { Check, ChevronDown, Clock, Close, Lock, More, Save as SaveIcon, Warning } from "./Icons";

import { copyText } from "../domain/clipboard";
import { ActionMenu } from "./ActionMenu";
import { display } from "../domain/keys";

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
  /** Copy a link that opens this document in this app. */
  onCopyLink?: () => void;
  /** Markdown only: show the RENDERED document instead of the source. A `.md` file is prose, and
   *  opening it as source means its headings, links and formulas arrive as raw syntax (007 MD-7). */
  preview?: { on: boolean; onToggle: () => void };
}

export function DocumentBar({
  doc, crumbs, language, fence, readOnly, dirty, saving, busy, notice, path,
  onReload, onSave, onAsk, onAttach, onOpenInDatabricks, onCopyLink, preview,
}: Props) {
  const [copied, setCopied] = useState(false);
  useEffect(() => { if (!copied) return; const timer = setTimeout(() => setCopied(false), 1500); return () => clearTimeout(timer); }, [copied]);
  const copyPath = () => { void copyText(path).then(setCopied); };
  const Icon = readOnly ? Lock : fence.tone === "ok" ? Check : fence.tone === "warn" ? Warning : Lock;
  const actions = ACTIONS_FOR[doc.kind];

  return (
    <>
    <header className="doc-bar">
      {/* Identity: name, language, breadcrumb — the things you need to know where you are. */}
      <div className="doc-id">
        <span className="doc-name" title={path}>{doc.name}</span>
        {language && <span className="doc-lang">{language}</span>}
        <button className="doc-crumbs" title={`${path} — click to copy`}
          aria-label={`Copy the path ${path}`}
          onClick={copyPath}>
          {copied ? "copied" : crumbs.slice(0, -1).map((c, i) => (
            <span key={`${c}-${i}`} className="crumb">
              {i > 0 && <span className="crumb-sep" aria-hidden>/</span>}
              {c}
            </span>
          ))}
        </button>
      </div>

      <span className="doc-bar-spacer" />



      {/* Fence: present before the first keystroke (WR-5), and never colour-only (UX-5). */}
      <span className={`fence-chip fence-${fence.tone}`} title={readOnly ? "this document is too large to save back safely" : fence.reason || "you can save here"}>
        <Icon size={13} />
        <span className="fence-text">{fence.label}</span>
      </span>

      {preview && (
        <button className={`btn sm preview-toggle${preview.on ? " is-on" : ""}`}
          aria-pressed={preview.on}
          aria-label={preview.on ? "Show the markdown source" : "Preview the rendered markdown"}
          title={preview.on ? "Show the source" : "Preview the rendered markdown"}
          onClick={preview.onToggle}>
          {preview.on ? "Source" : "Preview"}
        </button>
      )}

      <ActionMenu label="Ask the agent" className="btn sm ask-btn" title="Ask the agent about this document"
        actions={[{ label: "Add to chat", onSelect: onAttach }, ...actions.map((action) => ({ label: ACTIONS[action].label, onSelect: () => onAsk(action) }))]}>
        Ask <ChevronDown size={12} />
      </ActionMenu>
      <ActionMenu label="Document actions" className="icon-btn doc-more" description={readOnly ? "This document is read-only." : fence.reason || fence.label} actions={[
        { label: "Reload this document", onSelect: onReload, disabled: busy },
        ...(onCopyLink ? [{ label: "Copy document link", onSelect: onCopyLink }] : []),
        { label: "Copy document path", onSelect: copyPath },
        { label: "Open in Databricks", onSelect: onOpenInDatabricks },
      ]}><More size={16} /></ActionMenu>

      <button className="btn primary sm doc-save" onClick={onSave} disabled={readOnly || saving || !dirty}
        title={readOnly ? "This document cannot be saved" : `Save (${display("mod+s")})`}>
        {saving ? <Clock size={14} className="icon-spin" /> : <SaveIcon size={14} />}
        <span>Save</span>
      </button>
    </header>
    <span className="sr-only" role="status">{copied ? "Document path copied" : ""}</span>
    {notice && <div className={`doc-feedback is-${notice.tone}`} role={notice.tone === "error" ? "alert" : "status"}>{notice.text}</div>}
    </>
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
