/** The two controls Genie Code keeps in its panel header: history, and the conversation's own menu.
 *
 * History is the rail's `SessionList` in a popover, so a conversation can be found and reopened
 * without leaving the document you are working on, and the two lists cannot disagree because they are
 * one component. The menu holds what you do WITH a conversation: copy it, download it, start another.
 *
 * Both are popovers that close on Escape and on an outside press, and give focus back to the button
 * that opened them: a popover that traps you, or drops you at the top of the page, is worse than none.
 */
import { useEffect, useRef, useState, type ReactNode } from "react";
import { copyText } from "../domain/clipboard";
import { Check, Clock, Download, More, Plus } from "./Icons";
import { SessionList } from "./SessionList";
import type { SessionLike } from "../domain/sessions";

function usePopover() {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLSpanElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    const down = (e: MouseEvent) => { if (!root.current?.contains(e.target as Node)) setOpen(false); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") { setOpen(false); trigger.current?.focus(); } };
    window.addEventListener("mousedown", down);
    window.addEventListener("keydown", key);
    return () => { window.removeEventListener("mousedown", down); window.removeEventListener("keydown", key); };
  }, [open]);
  return { open, setOpen, root, trigger };
}

export function DockHistory<T extends SessionLike>({ sessions, activeId, onOpen, onDelete }: {
  sessions: T[]; activeId: string | null; onOpen: (s: T) => void; onDelete: (s: T) => Promise<void>;
}) {
  const { open, setOpen, root, trigger } = usePopover();
  return (
    <span className="dock-pop-wrap" ref={root}>
      <button ref={trigger} type="button" className="icon-btn" aria-haspopup="dialog" aria-expanded={open}
        title="Conversation history" aria-label="Conversation history" onClick={() => setOpen((o) => !o)}>
        <Clock size={14} />
      </button>
      {open && (
        <div className="dock-pop dock-history" role="dialog" aria-label="Conversation history">
          <div className="dock-pop-head">
            <strong>History</strong>
            <span>{sessions.length} {sessions.length === 1 ? "conversation" : "conversations"}</span>
          </div>
          <SessionList sessions={sessions} activeId={activeId}
            onOpen={(s) => { setOpen(false); onOpen(s); }} onDelete={onDelete} />
        </div>
      )}
    </span>
  );
}

export function DockMenu({ hasTurns, markdown, fileName, onNew }: {
  hasTurns: boolean;
  /** Produced on demand: a long conversation is not serialised on every render. */
  markdown: () => string;
  fileName: string;
  onNew: () => void;
}) {
  const { open, setOpen, root, trigger } = usePopover();
  const [copied, setCopied] = useState<"" | "done" | "failed">("");
  useEffect(() => { if (!open) setCopied(""); }, [open]);

  const copy = async () => {
    setCopied((await copyText(markdown())) ? "done" : "failed");
    window.setTimeout(() => setOpen(false), 900);
  };
  const download = () => {
    const url = URL.createObjectURL(new Blob([markdown()], { type: "text/markdown;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url; a.download = fileName; a.click();
    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    setOpen(false);
  };
  const item = (icon: ReactNode, label: string, run: () => void, disabled = false, hint?: string) => (
    <button role="menuitem" type="button" className="dock-menu-item" disabled={disabled} title={disabled ? "Nothing to export yet" : hint}
      onClick={run}>{icon}<span>{label}</span></button>
  );
  return (
    <span className="dock-pop-wrap" ref={root}>
      <button ref={trigger} type="button" className="icon-btn" aria-haspopup="menu" aria-expanded={open}
        title="More" aria-label="More conversation actions" onClick={() => setOpen((o) => !o)}><More size={14} /></button>
      {open && (
        <div className="dock-pop dock-menu" role="menu" aria-label="Conversation actions">
          {item(copied === "done" ? <Check size={13} /> : <span className="dock-menu-glyph" aria-hidden>⧉</span>,
            copied === "done" ? "Copied as Markdown" : copied === "failed" ? "Copy failed" : "Copy conversation", () => void copy(), !hasTurns)}
          {item(<Download size={13} />, "Download as Markdown", download, !hasTurns)}
          <div className="dock-menu-sep" role="separator" />
          {item(<Plus size={13} />, "New conversation", () => { setOpen(false); onNew(); }, false, "⌘⇧N")}
        </div>
      )}
    </span>
  );
}
