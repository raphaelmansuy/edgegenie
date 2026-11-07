/** Composer: message box, context chips, and the "@" picker for notebooks, files, tables.
 *
 * Context chips are references. Typing "@" searches the workspace by name; the files and catalog
 * trees add chips too. A chip marked "open" is the document on screen: it rides along with the
 * message automatically, the way Genie Code knows which notebook you are looking at.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { api, type CatalogItem, type WsHit } from "../api/client";
import { applyCommand, commandAt, matchCommands, pushHistory, stepHistory, type Command } from "../domain/commands";
import type { Attachment } from "../domain/events";
import type { Doc } from "../domain/docs";

const MENTION = /(^|\s)@([^\s@]*)$/;
const HISTORY_KEY = "coding-agent:prompt-history";

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

export function Composer({ disabled, busy, onSend, onStop, attachments, auto, onAdd, onRemove, openDocs, placeholder, inputRef }: {
  disabled?: boolean; busy: boolean; onSend: (text: string) => Promise<void>; onStop: () => void;
  /** Lets the app focus the box from a shortcut (⌘L) without prop-drilling a callback. */
  inputRef?: { current: HTMLTextAreaElement | null };
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
  const [tables, setTables] = useState<CatalogItem[]>([]);
  const [histAt, setHistAt] = useState(-1);
  const [history, setHistory] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem(HISTORY_KEY) ?? "[]"); } catch { return []; }
  });
  const own = useRef<HTMLTextAreaElement>(null);
  const ref = inputRef ?? own;

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [text]);

  const m = MENTION.exec(text.slice(0, caret));
  const query = m ? m[2] : null;
  const open = query !== null && dismissed !== `${caret}:${text}`;
  const cmd = commandAt(text, caret);
  const cmdOpen = cmd.open && cmd.query.length > 0 && dismissed !== `c:${caret}:${text}`;
  const commands: Command[] = cmdOpen ? matchCommands(cmd.query) : [];

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

  // tables are searched server-side (Unity Catalog has no name search endpoint), debounced like files
  useEffect(() => {
    if (query === null || query.length < 2) { setTables([]); return; }
    let live = true;
    const id = window.setTimeout(() => {
      api.findTables(query).then((r) => live && setTables(r.results)).catch(() => live && setTables([]));
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
    // An open document says so; an open table also says where it lives, so two `trips` in
    // different schemas are told apart.
    openDocs.filter((d) => !q || d.name.toLowerCase().includes(q) || d.ref.toLowerCase().includes(q))
      .forEach((d) => add({ kind: d.kind, ref: d.ref, name: d.name },
        d.kind === "table" ? d.ref.split(".").slice(0, -1).join(".") : "open"));
    found.forEach((h) => add({ kind: h.kind === "notebook" ? "notebook" : "file", ref: h.path, name: h.name },
      h.path.split("/").slice(0, -1).join("/")));
    // the hint is where the table lives, so two `trips` in different schemas are told apart
    tables.forEach((t) => add({ kind: "table", ref: t.ref, name: t.name },
      t.ref.split(".").slice(0, -1).join(".") || "table"));
    return out;
  }, [query, found, tables, openDocs, attachments]);

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
    setHistAt(-1);
    const next = pushHistory(history, value);
    setHistory(next);
    try { localStorage.setItem(HISTORY_KEY, JSON.stringify(next)); } catch { /* private mode */ }
    try { await onSend(value); } finally { setSending(false); }
  };

  const useHistory = (key: "ArrowUp" | "ArrowDown") => {
    const r = stepHistory(history, histAt, key);
    setHistAt(r.at);
    setText(r.text ?? "");
    requestAnimationFrame(() => {
      const el = ref.current;
      if (!el) return;
      el.setSelectionRange(el.value.length, el.value.length);
      setCaret(el.value.length);
    });
  };

  const pickCommand = (c: Command) => {
    const r = applyCommand(text, caret, c);
    setText(r.text);
    setCaret(r.caret);
    setDismissed("");
    requestAnimationFrame(() => {
      const el = ref.current;
      if (!el) return;
      el.focus();
      el.setSelectionRange(r.caret, r.caret);
    });
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
    <section className="composer" role="region" aria-label="Message the agent">
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
              if (cmdOpen && (e.key === "Enter" || e.key === "Tab") && commands[0]) {
                e.preventDefault(); pickCommand(commands[0]); return;
              }
              if (cmdOpen && e.key === "Escape") { e.preventDefault(); setDismissed(`c:${caret}:${text}`); return; }
              // Up/Down browse history only on a single-line box, so they never fight a long draft
              if (!open && !cmdOpen && (e.key === "ArrowUp" || e.key === "ArrowDown") && !text.includes("\n")) {
                const r = stepHistory(history, histAt, e.key);
                if (r.at !== -1 || histAt !== -1) { e.preventDefault(); useHistory(e.key); return; }
              }
              // Enter sends and Shift+Enter breaks the line, which is what every chat box does now.
              // ⌘⏎ still works for people who learned it here.
              if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void submit(); }
              if (e.key === "Escape" && busy) { e.preventDefault(); onStop(); }
            }}
            disabled={disabled}
          />
          {cmdOpen && (
            <div className="mention" role="listbox" aria-label="Commands">
              {commands.length === 0 && <div className="mention-empty">No command starts with “{cmd.query}”.</div>}
              {commands.map((c, i) => (
                <button key={c.name} role="option" aria-selected={i === 0}
                  className={`mention-opt${i === 0 ? " is-active" : ""}`}
                  onMouseDown={(e) => { e.preventDefault(); pickCommand(c); }}>
                  <span aria-hidden>/</span>
                  <span className="mention-name">{c.name.slice(1)}</span>
                  <span className="mention-hint">{c.hint}</span>
                </button>
              ))}
            </div>
          )}
          {open && (
            <div className="mention" role="listbox" aria-label="Add context">
              {options.length === 0 && (
                <div className="mention-empty">
                  {searching ? "Searching the workspace…"
                    : (query ?? "").length < 2 ? "Type two letters of a notebook, file, folder or table"
                      : "Nothing matches that name."}
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
          {/* Tools on the left, the primary action on the right: the reading order of every chat UI. */}
          <button className="btn ghost icon-btn" aria-label="Add a notebook, file or table" title="Add context (⌘⇧A)" onClick={mention} disabled={disabled}>＠</button>
          <button className="btn ghost icon-btn" aria-label="Commands" title="Commands (/)" disabled={disabled}
            onClick={() => {
              const el = ref.current;
              const at = el?.selectionStart ?? text.length;
              const lead = at > 0 && !/\s/.test(text[at - 1]) ? " " : "";
              const next = `${text.slice(0, at)}${lead}/${text.slice(at)}`;
              setText(next); setCaret(at + lead.length + 1);
              requestAnimationFrame(() => { el?.focus(); el?.setSelectionRange(at + lead.length + 1, at + lead.length + 1); });
            }}>/</button>
          <span className="hint"><kbd>⏎</kbd> send · <kbd>⇧⏎</kbd> new line</span>
          {busy ? (
            <button className="btn stop" onClick={onStop}>Stop <kbd>Esc</kbd></button>
          ) : (
            <button className="btn primary" onClick={() => void submit()} disabled={!text.trim() || disabled}>
              Send <kbd>⌘⏎</kbd>
            </button>
          )}
        </div>
      </div>
    </section>
  );
}
