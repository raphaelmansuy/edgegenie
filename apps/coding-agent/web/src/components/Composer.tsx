/** Composer: message box, context chips, and the "@" picker for notebooks, files, tables.
 *
 * Context chips are references. Typing "@" searches the workspace by name; the files and catalog
 * trees add chips too. A chip marked "open" is the document on screen: it rides along with the
 * message automatically, the way Genie Code knows which notebook you are looking at.
 */
import { createElement, useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react";
import { api, type CatalogItem, type WsHit } from "../api/client";
import { applyCommand, commandAt, matchCommands, pushHistory, stepHistory, type Command } from "../domain/commands";
import type { Attachment } from "../domain/events";
import { reasonText, type BlockedReason } from "../domain/compose";
import { canAttach, type Doc } from "../domain/docs";
import { ACCEPT } from "../domain/blob";
import { AttachMenu } from "./AttachMenu";
import { Chip } from "./Chip";
import { FileIcon, Folder, Notebook, Table } from "./Icons";
import { useBlobUpload } from "../hooks/useBlobUpload";

const MENTION = /(^|\s)@([^\s@]*)$/;
const HISTORY_KEY = "coding-agent:prompt-history";

/** One source of truth for "what does a notebook look like" across chips, tabs, and mentions. */
export const KIND_ICON: Record<string, (p: { size?: number }) => ReactNode> = {
  notebook: Notebook, file: FileIcon, folder: Folder, table: Table, blob: FileIcon,
};

/** Kept for callers that already import it from here; the implementation moved to `Chip.tsx`. */
export { Chip } from "./Chip";

interface Option { a: Attachment; hint: string }

export function Composer({ blockedReason: why, busy, onSend, onStop, attachments, auto, onAdd, onRemove, openDocs, placeholder, inputRef,
  variant = "main", compact = false, modelSlot, searchRoot, sessionId = null, modelSeesImages = true, modelName }: {
  /** `mine` is what THIS composer holds: ready blobs, which the parent's `attachments` cannot know about. */
  /** Why this composer cannot accept text, or null when it can.
   *
   *  This used to be a `disabled: boolean` computed at FOUR call sites from the connection state,
   *  which is how the reported defect happened and why two composers disagreed about one session
   *  (specs/012 02 §F7). It is now the reason from `domain/compose`, so the component cannot be told
   *  "disabled" without also being told why, and the connection cannot reach it at all. */
  blockedReason?: BlockedReason | null; busy: boolean;
  onSend: (text: string, mine?: Attachment[]) => Promise<void>; onStop: () => void;
  /** Lets the app focus the box from a shortcut (⌘L) without prop-drilling a callback. */
  inputRef?: { current: HTMLTextAreaElement | null };
  attachments: Attachment[]; auto?: Attachment | null;
  onAdd: (a: Attachment) => void; onRemove: (a: Attachment) => void;
  openDocs: Doc[]; placeholder?: string;
  /** `dock` narrows the padding and drops the max-width; it changes no behaviour (spec 006 D6). */
  variant?: "main" | "dock";
  compact?: boolean;
  /** The model control, placed in the action row so choosing a model never leaves the message (MC-3). */
  modelSlot?: React.ReactNode;
  /**
   * The root an `@` search walks. Before this the composer called `api.search(q)` with no root, so the
   * server used the user's home folder and files under /Shared or /Repos were unfindable (FX-6).
   */
  searchRoot?: string;
  /** The session the composer writes into: a blob upload is scoped to it, and the fence judges by it. */
  sessionId?: string | null;
  /** Whether the active model can consume an image, so an impossible attachment is refused before upload. */
  modelSeesImages?: boolean;
  /** The model's own name, for the refusal sentence. */
  modelName?: string;
}) {
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  /** `blocked` is DERIVED, never passed as a boolean: one reason in, one presentation out. */
  const blocked = Boolean(why);
  const blockedText = why ? reasonText(why) : "";
  const blockedReasonId = useId();
  /** Why the last send did not go, in the server's words. Cleared as soon as the user edits. */
  const [failure, setFailure] = useState("");
  const [caret, setCaret] = useState(0);
  const [found, setFound] = useState<WsHit[]>([]);
  const [searching, setSearching] = useState(false);
  const [pick, setPick] = useState(0);
  const [cmdPick, setCmdPick] = useState(0);
  const [dismissed, setDismissed] = useState("");
  const [tables, setTables] = useState<CatalogItem[]>([]);
  const [histAt, setHistAt] = useState(-1);
  const [history, setHistory] = useState<string[]>(() => {
    try { return JSON.parse(localStorage.getItem(HISTORY_KEY) ?? "[]"); } catch { return []; }
  });
  const own = useRef<HTMLTextAreaElement>(null);
  const ref = inputRef ?? own;
  /* Bytes the user hands us. The hook owns the chip list AND the upload; the composer only draws it.
     It deliberately does NOT mirror ready blobs into `onAdd`: doing that put every pasted file in the
     composer twice — once from the hook, once from the parent's attachment list — which measured as two
     identical chips per paste. The blobs reach the message through `onSend`'s second argument instead, so
     there is exactly one list of them (spec 009 [D1], [P5]). */
  const blobs = useBlobUpload(sessionId);
  const [dragging, setDragging] = useState(false);

  const attachCount = () => attachments.filter((a) => a.kind === "blob").length + blobs.chips.length;

  const accept = (files: FileList | File[]) => {
    const list = Array.from(files);
    if (list.length === 0) return;
    blobs.add(list, { count: attachCount(), modelSeesImages, model: modelName });
  };

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
  const cmdOpen = cmd.open && dismissed !== `c:${caret}:${text}`;
  const commands: Command[] = cmdOpen ? matchCommands(cmd.query) : [];

  useEffect(() => {
    if (query === null || query.length < 2) { setFound([]); return; }
    let live = true;
    setSearching(true);
    const id = window.setTimeout(() => {
      api.search(query, searchRoot).then((r) => live && setFound(r.results.filter((x) => x.kind !== "directory").slice(0, 8)))
        .catch(() => live && setFound([])).finally(() => live && setSearching(false));
    }, 300);
    return () => { live = false; window.clearTimeout(id); };
  }, [query, searchRoot]);

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
    // Only what the server can re-read is offerable: a project or an app is not attachable content
    // (spec 013 [UI-5]), so it is not in this list. The palette finds them instead.
    openDocs.filter((d) => canAttach(d.kind))
      .filter((d) => !q || d.name.toLowerCase().includes(q) || d.ref.toLowerCase().includes(q))
      .forEach((d) => {
        if (!canAttach(d.kind)) return;          // the predicate, where the narrowing happens
        add({ kind: d.kind, ref: d.ref, name: d.name },
          d.kind === "table" ? d.ref.split(".").slice(0, -1).join(".") : "open");
      });
    found.forEach((h) => add({ kind: h.kind === "notebook" ? "notebook" : "file", ref: h.path, name: h.name },
      h.path.split("/").slice(0, -1).join("/")));
    // the hint is where the table lives, so two `trips` in different schemas are told apart
    tables.forEach((t) => add({ kind: "table", ref: t.ref, name: t.name },
      t.ref.split(".").slice(0, -1).join(".") || "table"));
    return out;
  }, [query, found, tables, openDocs, attachments]);

  useEffect(() => setPick(0), [query]);
  useEffect(() => setCmdPick(0), [cmd.query, cmd.open]);

  const choose = (o: Option) => {
    onAdd(o.a);
    const before = text.slice(0, caret).replace(MENTION, "$1");
    setText(before + text.slice(caret));
    setCaret(before.length);
    requestAnimationFrame(() => { ref.current?.focus(); ref.current?.setSelectionRange(before.length, before.length); });
  };

  const submit = async () => {
    const value = text.trim();
    if (!value || sending || blocked || blobs.busy) return;
    setSending(true);
    setFailure("");
    setText("");
    setHistAt(-1);
    const next = pushHistory(history, value);
    setHistory(next);
    try { localStorage.setItem(HISTORY_KEY, JSON.stringify(next)); } catch { /* private mode */ }
    try {
      // Ready blobs, in the order they were attached. A failed chip is deliberately not sent: its bytes
      // never landed, and the user can still retry or remove it.
      const mine: Attachment[] = blobs.chips
        .filter((c) => c.state === "ready" && c.blobId)
        .map((c) => ({ kind: "blob" as const, ref: c.blobId as string, name: c.name }));
      await onSend(value, mine);
      // Sent, so the composer's chips are no longer a draft: the transcript owns them now. A CHIP THAT
      // FAILED is not sent, so it stays with its sentence to be retried or removed.
      blobs.clear();
      blobs.setNotice("");
    } catch (e) {
      // A refusal (no key for the model, no permission, the server down) must not eat the message:
      // put it back and say why, so fixing the cause and pressing Enter is all that is left to do.
      setText(value);
      setFailure(e instanceof Error && e.message ? e.message : "The message could not be sent.");
    } finally { setSending(false); }
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
    <section className={`composer${variant === "dock" ? " is-dock" : ""}${compact ? " is-compact" : ""}`} data-has-text={!!text.trim()} role="region"
      aria-label={variant === "dock" ? "Message the assistant" : "Message composer"}>
      <div className={`composer-box${blocked ? " is-blocked" : ""}`}>
        {(attachments.length > 0 || auto || blobs.chips.length > 0) && (
          <div className={`ctx-row${auto && !attachments.length && !blobs.chips.length ? " is-auto-only" : ""}`} aria-label="Context for this message">
            {auto && !attachments.some((x) => x.ref === auto.ref) && <Chip a={auto} auto />}
            {attachments.filter((a) => a.kind !== "blob").map((a) => (
              <Chip key={`${a.kind}:${a.ref}`} a={a} onRemove={() => onRemove(a)} />
            ))}
            {blobs.chips.map((c) => (
              <Chip
                key={c.key}
                a={{ kind: "blob", ref: c.blobId ?? c.key, name: c.name }}
                state={c.state}
                reason={c.reason}
                // An image on a model with no vision is still attached; the chip says what the model gets.
                unseen={!modelSeesImages && /^image\//.test(c.mime ?? "")}
                onRetry={c.state === "failed" ? () => blobs.retry(c.key, {
                  count: attachCount(), modelSeesImages, model: modelName }) : undefined}
                onRemove={() => blobs.remove(c.key)}
              />
            ))}
          </div>
        )}
        {(blobs.notice || blobs.chips.some((c) => c.state === "failed")) && (
          <p className="composer-error" role="alert">
            {blobs.notice || blobs.chips.find((c) => c.state === "failed")?.reason}
          </p>
        )}
        {failure && (
          <p className="composer-error" role="alert">
            {failure}
            {/needs a key|API key|credential/i.test(failure) && <> Add one in <kbd>⌘ ,</kbd> Providers and keys.</>}
          </p>
        )}
        <div
          className={`composer-field${dragging ? " is-dropping" : ""}`}
          onDragOver={(e) => {
            if (!e.dataTransfer?.types.includes("Files")) return;
            e.preventDefault();          // required, or the browser opens the file
            setDragging(true);
          }}
          onDragLeave={(e) => {
            // Only when the pointer leaves the FIELD, not when it crosses into a child.
            if (e.currentTarget.contains(e.relatedTarget as Node | null)) return;
            setDragging(false);
          }}
          onDrop={(e) => {
            if (!e.dataTransfer?.files?.length) return;
            e.preventDefault();
            setDragging(false);
            accept(e.dataTransfer.files);
          }}
        >
          {dragging && (
            <div className="drop-hint" aria-hidden>
              <span className="drop-hint-big">Drop to attach</span>
              <span className="drop-hint-small">{ACCEPT.replace(/\./g, "").replace(/,/g, " · ")}</span>
            </div>
          )}
          <textarea
            ref={ref}
            value={text}
            /* A blocked composer is `readOnly`, NEVER `disabled`.
             *
             * `disabled` removes a form control from the tab order and from the accessibility tree's
             * focus, so a keyboard or screen-reader user could not reach the one place they are
             * supposed to write — and `⌘L`, which promises to focus it, silently did nothing. That
             * was the reported defect (specs/012 02 §F1, §F3).
             *
             * `readOnly` refuses edits exactly as firmly; it only stops pretending the control is not
             * there. Combined with `aria-disabled` and a described reason, the box stays reachable and
             * explains itself in place. [FX-1] [FX-2] */
            readOnly={Boolean(blocked)}
            aria-disabled={blocked ? true : undefined}
            aria-describedby={blocked ? blockedReasonId : undefined}
            placeholder={blocked ? blockedText : (placeholder ?? "Ask for a notebook, a job, a fix, an investigation…   @ adds a notebook, file or table")}
            aria-label="Message the agent"
            aria-description="Enter sends your message. Shift+Enter adds a new line."
            aria-autocomplete="list"
            aria-expanded={open}
            onPaste={(e) => {
              /* The single most important line in this handler: return BEFORE preventDefault when there is
                 nothing we can take, or pasting text stops working (spec 009 [E-14], [06 §Front-end]). */
              const files = Array.from(e.clipboardData?.files ?? []);
              if (files.length === 0) return;
              e.preventDefault();
              accept(files);
            }}
            onChange={(e) => { setText(e.target.value); setCaret(e.target.selectionStart); if (failure) setFailure(""); if (blobs.notice) blobs.setNotice(""); }}
            onSelect={(e) => setCaret((e.target as HTMLTextAreaElement).selectionStart)}
            onKeyDown={(e) => {
              if (open && (options.length > 0 || searching)) {
                if (e.key === "ArrowDown") { e.preventDefault(); setPick((p) => Math.min(p + 1, options.length - 1)); return; }
                if (e.key === "ArrowUp") { e.preventDefault(); setPick((p) => Math.max(p - 1, 0)); return; }
                if ((e.key === "Enter" || e.key === "Tab") && options[pick]) { e.preventDefault(); choose(options[pick]); return; }
              }
              if (open && e.key === "Escape") { e.preventDefault(); setDismissed(`${caret}:${text}`); return; }
              if (cmdOpen && commands.length > 0) {
                if (e.key === "ArrowDown") { e.preventDefault(); setCmdPick((p) => (p + 1) % commands.length); return; }
                if (e.key === "ArrowUp") { e.preventDefault(); setCmdPick((p) => (p - 1 + commands.length) % commands.length); return; }
                if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); pickCommand(commands[cmdPick] ?? commands[0]); return; }
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
            /* NOT `disabled`. See this element's attribute block above: `disabled` makes the field
               unfocusable, which is the reported defect. `readOnly` + `aria-disabled` refuse edits
               just as firmly while keeping the field reachable. [FX-1] [FX-2] */
          />
          {cmdOpen && (
            <div className="mention" role="listbox" aria-label="Commands">
              {commands.length === 0 && <div className="mention-empty">No command starts with “{cmd.query}”.</div>}
              {commands.map((c, i) => (
                <button key={c.name} role="option" aria-selected={i === cmdPick}
                  className={`mention-opt${i === cmdPick ? " is-active" : ""}`}
                  ref={(el) => { if (el && i === cmdPick) el.scrollIntoView({ block: "nearest" }); }}
                  onMouseDown={(e) => { e.preventDefault(); pickCommand(c); }}>
                  <span aria-hidden>/</span>
                  <span className="mention-name">{c.name.slice(1)}</span>
                  <span className="mention-hint is-cmd">{c.hint}</span>
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
                  <span className="chip-icon" aria-hidden>{createElement(KIND_ICON[o.a.kind] ?? FileIcon, { size: 13 })}</span>
                  <span className="mention-name">{o.a.name}</span>
                  <span className="mention-hint">{o.hint}</span>
                </button>
              ))}
            </div>
          )}
        </div>
        {/* The reason, once, linked by `aria-describedby`.
         *
         * Visually it is already in the placeholder, which is where a sighted user looks. A screen
         * reader gets it through this element instead — and it is NOT a tab stop, because inserting a
         * focusable "reason" ahead of the box would make a keyboard user Tab into a paragraph.
         * [FX-2] */}
        {blocked && (
          <p id={blockedReasonId} className="composer-blocked-reason" role="note">
            {blockedText}
          </p>
        )}
        <div className="composer-actions">
          {/* Tools on the left, the primary action on the right: the reading order of every chat UI. */}
          <AttachMenu
            disabled={blocked}
            onFiles={accept}
            onContext={mention}
          />
          <button className="btn ghost icon-btn" aria-label="Add a notebook, file or table" title="Add context (⌘⇧A)" onClick={mention} disabled={blocked}>＠</button>
          <button className="btn ghost icon-btn" aria-label="Commands" title="Commands (/)" disabled={blocked}
            onClick={() => {
              const el = ref.current;
              const at = el?.selectionStart ?? text.length;
              const lead = at > 0 && !/\s/.test(text[at - 1]) ? " " : "";
              const next = `${text.slice(0, at)}${lead}/${text.slice(at)}`;
              setText(next); setCaret(at + lead.length + 1);
              requestAnimationFrame(() => { el?.focus(); el?.setSelectionRange(at + lead.length + 1, at + lead.length + 1); });
            }}>/</button>
          {modelSlot}
          <span className="hint"><kbd>⏎</kbd> send · <kbd>⇧⏎</kbd> new line</span>
          {busy ? (
            <button className="btn stop" disabled={blocked} onClick={onStop}>Stop <kbd>Esc</kbd></button>
          ) : (
            <button className="btn primary" onClick={() => void submit()} disabled={!text.trim() || blocked || blobs.busy}
              title={blobs.busy
                ? `Waiting for ${blobs.chips.find((c) => c.state === "pending")?.name ?? "an attachment"} to finish uploading`
                : undefined}>
              Send <kbd>⌘⏎</kbd>
            </button>
          )}
        </div>
      </div>
    </section>
  );
}
