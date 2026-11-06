/** Composer: message box, context chips, and the "@" picker for notebooks, files, tables.
 *
 * Context chips are references. Typing "@" searches the workspace by name; the files and catalog
 * trees add chips too. A chip marked "open" is the document on screen: it rides along with the
 * message automatically, the way Genie Code knows which notebook you are looking at.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { api, type WsHit } from "../api/client";
import type { Attachment } from "../domain/events";
import type { Doc } from "../domain/docs";

const MENTION = /(^|\s)@([^\s@]*)$/;

export const KIND_GLYPH: Record<string, string> = { notebook: "▤", file: "▢", folder: "▸", table: "▦" };

export function Chip({ a, auto, onRemove }: { a: Attachment; auto?: boolean; onRemove?: () => void }) {
  return (
    <span className={`ctx-chip${auto ? " auto" : ""}`} title={`${a.ref}${auto ? "\nOpen in the viewer, so it is sent with your message" : ""}`}>
      <span aria-hidden>{KIND_GLYPH[a.kind]}</span>
      <span className="ctx-name">{a.name}</span>
      {auto && <span className="ctx-tag">open</span>}
      {onRemove && <button aria-label={`Remove ${a.name}`} onClick={onRemove}>×</button>}
    </span>
  );
}

interface Option { a: Attachment; hint: string }

export function Composer({ disabled, busy, onSend, onStop, attachments, auto, onAdd, onRemove, openDocs, placeholder }: {
  disabled?: boolean; busy: boolean; onSend: (text: string) => Promise<void>; onStop: () => void;
  attachments: Attachment[]; auto?: Attachment | null;
  onAdd: (a: Attachment) => void; onRemove: (a: Attachment) => void;
  openDocs: Doc[]; placeholder?: string;
}) {
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [caret, setCaret] = useState(0);
  const [found, setFound] = useState<WsHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [pick, setPick] = useState(0);
  const [dismissed, setDismissed] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [text]);

  const m = MENTION.exec(text.slice(0, caret));
  const query = m ? m[2] : null;
  const open = query !== null && dismissed !== `${caret}:${text}`;

  useEffect(() => {
    if (query === null || query.length < 2) { setFound([]); return; }
    let live = true;
    setSearching(true);
    const id = window.setTimeout(() => {
      api.search(query).then((r) => live && setFound(r.results.filter((x) => x.kind !== "directory").slice(0, 8)))
        .catch(() => live && setFound([])).finally(() => live && setSearching(false));
    }, 300);
    return () => { live = false; window.clearTimeout(id); };
  }, [query]);

  const options: Option[] = useMemo(() => {
    const q = (query ?? "").toLowerCase();
    const seen = new Set<string>();
    const out: Option[] = [];
    const add = (a: Attachment, hint: string) => {
      const k = `${a.kind}:${a.ref}`;
      if (!seen.has(k) && !attachments.some((x) => x.kind === a.kind && x.ref === a.ref)) { seen.add(k); out.push({ a, hint }); }
    };
    openDocs.filter((d) => !q || d.name.toLowerCase().includes(q) || d.ref.toLowerCase().includes(q))
      .forEach((d) => add({ kind: d.kind, ref: d.ref, name: d.name }, "open"));
    found.forEach((h) => add({ kind: h.kind === "notebook" ? "notebook" : "file", ref: h.path, name: h.name },
      h.path.split("/").slice(0, -1).join("/")));
    return out;
  }, [query, found, openDocs, attachments]);

  useEffect(() => setPick(0), [query]);

  const choose = (o: Option) => {
    onAdd(o.a);
    const before = text.slice(0, caret).replace(MENTION, "$1");
    setText(before + text.slice(caret));
    setCaret(before.length);
    requestAnimationFrame(() => { ref.current?.focus(); ref.current?.setSelectionRange(before.length, before.length); });
  };

  const submit = async () => {
    const value = text.trim();
    if (!value || sending || disabled) return;
    setSending(true);
    setText("");
    try { await onSend(value); } finally { setSending(false); }
  };

  const mention = () => {
    const el = ref.current;
    const at = el?.selectionStart ?? text.length;
    const lead = at > 0 && !/\s/.test(text[at - 1]) ? " " : "";
    const next = `${text.slice(0, at)}${lead}@${text.slice(at)}`;
    setText(next);
    const pos = at + lead.length + 1;
    setCaret(pos);
    requestAnimationFrame(() => { el?.focus(); el?.setSelectionRange(pos, pos); });
  };

  return (
    <div className="composer">
      <div className="composer-box">
        {(attachments.length > 0 || auto) && (
          <div className="ctx-row" aria-label="Context for this message">
            {auto && !attachments.some((x) => x.ref === auto.ref) && <Chip a={auto} auto />}
            {attachments.map((a) => <Chip key={`${a.kind}:${a.ref}`} a={a} onRemove={() => onRemove(a)} />)}
          </div>
        )}
        <div className="composer-field">
          <textarea
            ref={ref}
            value={text}
            placeholder={placeholder ?? "Ask for a notebook, a job, a fix, an investigation…   @ adds a notebook, file or table"}
            aria-label="Message the agent"
            aria-autocomplete="list"
            aria-expanded={open}
            onChange={(e) => { setText(e.target.value); setCaret(e.target.selectionStart); }}
            onSelect={(e) => setCaret((e.target as HTMLTextAreaElement).selectionStart)}
            onKeyDown={(e) => {
              if (open && (options.length > 0 || searching)) {
                if (e.key === "ArrowDown") { e.preventDefault(); setPick((p) => Math.min(p + 1, options.length - 1)); return; }
                if (e.key === "ArrowUp") { e.preventDefault(); setPick((p) => Math.max(p - 1, 0)); return; }
                if ((e.key === "Enter" || e.key === "Tab") && options[pick]) { e.preventDefault(); choose(options[pick]); return; }
              }
              if (open && e.key === "Escape") { e.preventDefault(); setDismissed(`${caret}:${text}`); return; }
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); void submit(); }
              if (e.key === "Escape" && busy) { e.preventDefault(); onStop(); }
            }}
            disabled={disabled}
          />
          {open && (
            <div className="mention" role="listbox" aria-label="Add context">
              {options.length === 0 && (
                <div className="mention-empty">
                  {searching ? "Searching the workspace…"
                    : (query ?? "").length < 2 ? "Type two letters of a notebook or file name"
                      : "No notebook or file matches. Tables: use the Catalog tab."}
                </div>
              )}
              {options.map((o, i) => (
                <button key={`${o.a.kind}:${o.a.ref}`} role="option" aria-selected={i === pick}
                  className={`mention-opt${i === pick ? " is-active" : ""}`}
                  onMouseDown={(e) => { e.preventDefault(); choose(o); }}>
                  <span aria-hidden>{KIND_GLYPH[o.a.kind]}</span>
                  <span className="mention-name">{o.a.name}</span>
                  <span className="mention-hint">{o.hint}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="composer-actions">
          <button className="btn ghost" aria-label="Add context" title="Add a notebook or file (@)" onClick={mention} disabled={disabled}>＠</button>
          {busy ? (
            <button className="btn stop" onClick={onStop}>⏹ Stop</button>
          ) : (
            <button className="btn primary" onClick={() => void submit()} disabled={!text.trim() || disabled}>Send</button>
          )}
          <span className="hint"><kbd>⌘</kbd><kbd>⏎</kbd> send · <kbd>Esc</kbd> stop</span>
        </div>
      </div>
    </div>
  );
}
