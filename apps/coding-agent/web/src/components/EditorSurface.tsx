/** The document editing surface: editor + fence + save + conflict, as one coherent thing.
 *
 * This is where spec 003 requirements meet a user:
 *
 *   WR-5  the fence is a chip in the bar, visible before the first keystroke
 *   ED-8  every change lands in a draft, so a reload or a crash loses nothing
 *   CX-1  the version the buffer was based on travels with it
 *   CX-3  a conflict is a *choice*, never an automatic resolution
 *   DF-1  an agent proposal is a diff you accept per hunk
 *
 * The component owns no document text in React state on purpose: `text` lives in the EditorHost and
 * reaches this component only when it needs to be saved. What it does track is the small amount of
 * state a user can see — dirty, saving, the fence verdict, and a pending conflict.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { askFence, saveDocument, type SaveResult } from "../api/save";
import { checkCells, parseCells, serializeCells, type Cell } from "../domain/notebook";
import { checkPath, describeFence } from "../domain/fence";
import { clear as clearDraft, read as readDraft, write as writeDraft } from "../domain/drafts";
import { Editor } from "../editor/Editor";
import { NotebookEditor } from "./NotebookEditor";
import { Check, Clock, Close, Lock, Save as SaveIcon, Warning } from "../components/Icons";
import { ConflictPanel } from "./ConflictPanel";

export interface EditTarget {
  /** Workspace path, e.g. `/Users/x/agent_scratch/notes.py`. */
  path: string;
  name: string;
  kind: "notebook" | "file";
  language: string;
  /** The version token the content was loaded at. `null` = a new object. */
  version: string | null;
  /** True when the reader truncated the content: saving would destroy the tail (ED-6, D7). */
  truncated: boolean;
}

interface Props {
  target: EditTarget;
  /** The writable folder of the current session, or "" when there is no session. */
  folder: string;
  sessionId: string | null;
  /** The loaded content: a SOURCE string for a notebook, raw text for a file. */
  source: string;
  theme: "light" | "dark";
  onSaved: (version: string | null) => void;
  /** Called with the derived cells on every change, so the parent can render notebook chrome. */
  onCells: (cells: Cell[]) => void;
  /** Ask the agent about one cell: the reason owning the editor is worth building (lens 7). */
  onAskCell?: (cell: Cell) => void;
}

const SAVE_DEBOUNCE = 150;

export function EditorSurface({
  target, folder, sessionId, source, theme, onSaved, onCells, onAskCell,
}: Props) {
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [fence, setFence] = useState(() => checkPath(folder, target.path));
  /** The server's answer, once we have it. It is the authority; the local check is a preview. */
  const [serverFence, setServerFence] = useState<{ verdict: string; reason: string } | null>(null);
  const [conflict, setConflict] = useState<Extract<SaveResult, { kind: "conflict" }> | null>(null);
  const [asking, setAsking] = useState<{ reason: string; token: string | null } | null>(null);
  const [notice, setNotice] = useState<{ tone: "ok" | "warn" | "error"; text: string } | null>(null);
  const [restored, setRestored] = useState(false);
  /** A recovery replaces the buffer through the same channel a load uses, because the editor is
   *  uncontrolled: this is the value the Editor is told to show. */
  const [forceValue, setForceValue] = useState<string | null>(null);

  /** The live text. A ref, not state: keystrokes must not re-render this component (ED-2). */
  const text = useRef(source);
  /** In notebook mode the cells ARE the document. They start empty and are seeded when `source`
   *  arrives: the first render has no data (the load is async), so seeding in `useState` would pin
   *  the editor to an empty document forever. */
  const [liveCells, setLiveCells] = useState<Cell[]>([]);
  const seeded = useRef(false);
  /** True while we are adopting text from above (a load, or the reload right after a save). A
   *  document we just wrote must not come back as "dirty": that would leave Save enabled forever
   *  and make the notice a lie. */
  const adopting = useRef(false);
  useEffect(() => {
    if (target.kind !== "notebook" || !source) return;
    const next = parseCells(source, target.language);
    // Re-seed when the document changes or when we have not seeded yet, and never while the user is
    // mid-edit in the same document.
    if (seeded.current && !adopting.current) return;
    seeded.current = true;
    adopting.current = true;
    setLiveCells(next);
    // The adoption turn ends after the cell stack has re-rendered with it.
    const t = window.setTimeout(() => { adopting.current = false; }, 0);
    return () => window.clearTimeout(t);
  }, [source, target.kind, target.language]);
  // A different document means a different cell list.
  useEffect(() => {
    seeded.current = false;
    adopting.current = false;
    setLiveCells([]);
  }, [target.path]);
  const saveTimer = useRef<number | undefined>(undefined);
  /** A real lock, not a state read: two key events in one tick both see the old `saving` value. */
  const inFlight = useRef(false);
  /** The version this buffer is based on.
   *
   * A ref, not `target.version`: the parent reloads after every save, and a prop captured at the
   * last render is stale by the time the next ⌘S fires. That staleness is a 409 on a save nobody
   * else raced with — which is exactly what made the e2e suite see a conflict on the first press.
   * `onSaved` writes the new token here, so the next save compares against what we just wrote.
   */
  const version = useRef<string | null>(target.version);
  useEffect(() => { version.current = target.version; }, [target.version, target.path]);

  const readOnly = target.truncated;

  useEffect(() => {
    setFence(checkPath(folder, target.path));
    setServerFence(null);
    // Ask the server what it thinks, so the chip matches what a save will actually do. Without
    // this, a session-less editor says "in your folder" and then the save is refused — the one
    // pairing that makes a fence feel arbitrary.
    let live = true;
    void askFence(target.path, sessionId, target.version ?? "").then((a) => {
      if (live) setServerFence({ verdict: a.verdict, reason: a.reason });
    });
    return () => { live = false; };
  }, [folder, target.path, sessionId, target.version]);

  // Offer a draft if one exists and differs from what the server gave us. Never apply it silently.
  useEffect(() => {
    const draft = readDraft(target.path);
    if (draft && draft.text !== source) setRestored(true);
    else setRestored(false);
    text.current = source;
  }, [target.path, source]);

  useEffect(() => {
    if (!notice) return;
    const t = window.setTimeout(() => setNotice(null), 4000);
    return () => window.clearTimeout(t);
  }, [notice]);

  const onChange = useCallback((next: string) => {
    text.current = next;
    setDirty(true);
    if (saveTimer.current) window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => {
      // The draft is written on a debounce, *before* any save: this is the guarantee CX-5 sells.
      writeDraft({ docId: target.path, text: next, basedOn: version.current ?? "", at: Date.now() });
    }, SAVE_DEBOUNCE);
    // A notebook's cells are derived, so the parent can show cell-level chrome (P4).
    if (target.kind === "notebook" && onCells) onCells(parseCells(next, target.language));
  }, [target.path, target.version, target.kind, target.language, onCells]);

  /** Persist. One path for ⌘S, the Save button, and "keep mine" after a conflict. */
  const save = useCallback(async (approved?: string) => {
    if (readOnly || inFlight.current) return;
    inFlight.current = true;
    const body = text.current;

    if (target.kind === "notebook") {
      const problems = checkCells(parseCells(body, target.language), target.language);
      if (problems.length) {
        setNotice({ tone: "error", text: `cannot save: ${problems[0]}` });
        inFlight.current = false;
        return;
      }
    }

    setSaving(true);
    setConflict(null);
    const result = await saveDocument({
      path: target.path, text: body, version: version.current,
      sessionId, approval: approved ?? null, language: target.language.toUpperCase(),
    });
    setSaving(false);
    inFlight.current = false;

    switch (result.kind) {
      case "ok":
        setDirty(false);
        clearDraft(target.path);
        setNotice({ tone: "ok", text: "saved" });
        version.current = result.version;      // the next save must compare against what we wrote
        onSaved(result.version);
        break;
      case "ask": {
        // The fence wants approval. The 403 carries the reason but not a token: an approval has to
        // be minted for this exact path and version, which is what /workspace/fence does. Without
        // this round trip the sheet would appear with no way to complete it — a dead end.
        const answer = await askFence(target.path, sessionId, version.current ?? "");
        setAsking({ reason: result.reason || answer.reason, token: answer.approval });
        break;
      }
      case "conflict":
        setConflict(result);
        break;
      case "error":
        setNotice({ tone: "error", text: result.message });
        break;
    }
  }, [onSaved, readOnly, saving, sessionId, target.kind, target.language, target.path, target.version]);

  /* ⌘S for when focus is *outside* the editor: the cell bar, the toolbar, the fence chip. When the
     editor has focus its own keymap handles the key, so this must not also fire — two handlers for
     one keypress means two saves, and the second one races the first into a 409 conflict. */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== "s") return;
      const t = e.target as HTMLElement | null;
      if (t?.closest(".cm-editor")) return;        // the editor's keymap owns it
      e.preventDefault();
      void save();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [save]);

  const restore = () => {
    const draft = readDraft(target.path);
    if (!draft) return;
    text.current = draft.text;
    setDirty(true);
    setRestored(false);
    setForceValue(draft.text);
    if (target.kind === "notebook" && onCells) onCells(parseCells(draft.text, target.language));
    setNotice({ tone: "ok", text: "draft restored" });
  };

  const approve = async () => {
    const token = asking?.token;
    setAsking(null);
    if (!token) {
      setNotice({ tone: "error", text: "could not get an approval for this path" });
      return;
    }
    await save(token);
  };

  // Prefer the server's verdict: it is what the save will be judged by.
  const effective = serverFence
    ? { verdict: serverFence.verdict as "allow" | "ask" | "deny", target: target.path, reason: serverFence.reason }
    : fence;
  const chip = describeFence(effective, readOnly);
  const Icon = readOnly ? Lock : chip.tone === "ok" ? Check : chip.tone === "warn" ? Warning : Lock;

  return (
    <section className="editor-surface" aria-label={`Editing ${target.name}`}>
      <header className="editor-bar">
        <span className={`fence-chip fence-${chip.tone}`} title={readOnly ? "this document is too large to save back safely" : fence.reason || "you can save here"}>
          <Icon size={13} />
          <span className="fence-text">{chip.label}</span>
        </span>

        <span className="editor-bar-spacer" />

        {dirty && <span className="editor-dirty" title="unsaved changes">unsaved</span>}
        {notice && <span className={`editor-notice is-${notice.tone}`} role="status">{notice.text}</span>}

        <button className="btn primary sm" onClick={() => void save()} disabled={readOnly || saving || !dirty}
          title={readOnly ? "this document cannot be saved" : "Save (⌘S)"}>
          {saving ? <Clock size={14} className="spin" /> : <SaveIcon size={14} />}
          <span>Save</span>
        </button>
      </header>

      {restored && (
        <div className="draft-banner" role="status">
          <Clock size={14} />
          <span>You have unsaved changes from earlier.</span>
          <button className="btn sm" onClick={restore}>Restore</button>
          <button className="btn ghost sm" aria-label="Discard the recovered draft" onClick={() => {
            clearDraft(target.path);
            setRestored(false);
          }}><Close size={12} /></button>
        </div>
      )}

      {readOnly && (
        <p className="editor-readonly-note" role="note">
          This document is larger than the viewer reads, so saving it would silently drop the rest.
          It is open read-only. Ask the agent to change it instead.
        </p>
      )}

      {conflict && (
        <ConflictPanel
          conflict={conflict}
          mine={text.current}
          theirs={null}
          onKeepMine={() => {
            // A deliberate overwrite: adopt the server's current version so the next save is not
            // fighting the check, and say so. The draft of the user's text is already on disk.
            setConflict(null);
            void save();
          }}
          onTakeTheirs={() => {
            setConflict(null);
            clearDraft(target.path);
            setDirty(false);
            setNotice({ tone: "ok", text: "their version is on disk — reload to see it" });
          }}
          onDismiss={() => setConflict(null)}
        />
      )}

      {asking && (
        <div className="ask-banner" role="alertdialog" aria-label="Approval required">
          <Warning size={15} />
          <div>
            <strong>Save outside your working folder?</strong>
            <p><code>{target.path}</code> — {asking.reason}</p>
          </div>
          <button className="btn primary sm" onClick={() => void approve()}>Allow once</button>
          <button className="btn ghost sm" onClick={() => setAsking(null)}>Cancel</button>
        </div>
      )}

      {/* Notebook mode: a stack of cells rather than one text buffer. This is the surface a
          notebook deserves (NB-1..NB-5), and it is the same document the save writes — the cells
          are serialized once, on save, by the same pure module the tests cover. */}
      {target.kind === "notebook" ? (
        <NotebookEditor
          cells={liveCells}
          language={target.language}
          theme={theme}
          readOnly={readOnly}
          onChange={(next) => {
            setLiveCells(next);
            if (adopting.current) return;      // this is the reload after a save, not an edit
            // One serialization, in the ref, so save and draft read the same bytes the cells mean.
            const serialized = serializeCells(next, target.language);
            text.current = serialized;
            setDirty(true);
            writeDraft({ docId: target.path, text: serialized, basedOn: target.version ?? "", at: Date.now() });
            onCells(next);
          }}
          onAskCell={(cell) => onAskCell?.(cell)}
        />
      ) : (
        <Editor
          value={forceValue ?? source}
          language={target.language}
          readOnly={readOnly}
          theme={theme}
          onChange={onChange}
          onSave={() => void save()}
          autoFocus
          ariaLabel={`${target.name} source`}
        />
      )}
    </section>
  );
}
