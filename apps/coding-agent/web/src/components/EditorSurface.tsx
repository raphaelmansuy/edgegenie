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
import { Clock, Close, Warning } from "../components/Icons";
import { ConflictPanel } from "./ConflictPanel";
import { crumbsOf, DocumentBar } from "./DocumentBar";
import type { Action } from "../domain/docs";

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
  /** The bar's actions. The surface does not own "ask the agent"; the app does. */
  onAskAction?: (a: Action) => void;
  onAttach?: () => void;
  onOpenInDatabricks?: () => void;
  onReload?: () => void;
}

const SAVE_DEBOUNCE = 150;

export function EditorSurface({
  target, folder, sessionId, source, theme, onSaved, onCells, onAskCell,
  onAskAction, onAttach, onOpenInDatabricks, onReload,
}: Props) {
  useEffect(() => {
    const w = window as unknown as { __m?: string[] };
    w.__m = w.__m || [];
    w.__m.push(`mount ${Math.random().toString(36).slice(2, 6)}`);
    return () => { w.__m!.push(`unmount ${Math.random().toString(36).slice(2, 6)}`); };
  }, []);
  const [dirty, setDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [fence, setFence] = useState(() => checkPath(folder, target.path));
  /** The server's answer, once we have it. It is the authority; the local check is a preview. */
  const [serverFence, setServerFence] = useState<{ verdict: string; reason: string } | null>(null);
  const [conflict, setConflict] = useState<Extract<SaveResult, { kind: "conflict" }> | null>(null);
  const [asking, setAsking] = useState<{ reason: string; token: string | null; noFolder: boolean } | null>(null);
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
  /** The text this buffer is showing, as we last accepted it from above. An incoming `source` that
   *  equals it is not a change, so adopting it must not mark the document dirty. */
  const accepted = useRef<string>("");
  useEffect(() => {
    if (target.kind !== "notebook" || !source) return;
    if (seeded.current) return;
    seeded.current = true;
    accepted.current = source;
    setLiveCells(parseCells(source, target.language));
  }, [source, target.kind, target.language]);

  /* After a save, the parent reloads and hands us new `source`. That is not an edit, so it must not
     mark the document dirty — but the old value of `source` is gone by then, so a byte comparison
     against it cannot work. What can work: the cells we just saved. If the incoming text parses to
     the same cells, it is our own write coming back. Compared by meaning, not by bytes, because the
     parent may serialize with different (equally valid) spacing. */
  const savedCells = useRef<Cell[] | null>(null);
  useEffect(() => {
    if (target.kind !== "notebook" || !source || !savedCells.current) return;
    const incoming = parseCells(source, target.language);
    const same = incoming.length === savedCells.current.length
      && incoming.every((c, i) => c.kind === savedCells.current![i].kind
        && c.source === savedCells.current![i].source);
    if (same) {
      savedCells.current = null;
      setDirty(false);            // our own bytes: the buffer is exactly what is on disk
    }
  }, [source, target.kind, target.language]);
  // A different document means a different cell list.
  useEffect(() => {
    seeded.current = false;
    accepted.current = "";
    setLiveCells([]);
  }, [target.path]);
  const saveTimer = useRef<number | undefined>(undefined);
  /** A real lock, not a state read: two key events in one tick both see the old `saving` value. */
  const inFlight = useRef(false);
  /** The latest `save`, for the single window listener. */
  const saveRef = useRef<() => void>(() => {});
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
        // Remember what we wrote, so the reload that follows is recognised as an echo, not an edit.
        savedCells.current = liveCells.length ? liveCells : parseCells(body, target.language);
        clearDraft(target.path);
        setNotice({ tone: "ok", text: "saved" });
        version.current = result.version;      // the next save must compare against what we wrote
        /* `onSaved` reloads the document from the server. If that throws — a transient read error,
           a dropped connection — the save has still happened, and letting the exception escape
           would leave `saving` stuck true, which disables Save forever and keeps the spinner
           turning. A failed reload is not a failed save, and the UI must say so. */
        try {
          onSaved(result.version);
        } catch {
          setNotice({ tone: "warn", text: "saved — reload failed, so the view may be stale" });
        }
        break;
      case "ask": {
        // The fence wants approval. The 403 carries the reason but not a token: an approval has to
        // be minted for this exact path and version, which is what /workspace/fence does. Without
        // this round trip the sheet would appear with no way to complete it — a dead end.
        const answer = await askFence(target.path, sessionId, version.current ?? "");
        const reason = result.reason || answer.reason;
        setAsking({
          reason,
          token: answer.approval,
          // The server says exactly this when there is no session; the fence has no folder, so the
          // heading should not claim one exists.
          noFolder: reason.toLowerCase().includes("no session"),
        });
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

  /* Keep the ref current so the single window listener always calls the latest closure. This runs
     on every render and is the only cost of registering the listener once. */
  saveRef.current = () => { void save(); };

  /* ⌘S for when focus is *outside* the editor: the cell bar, the toolbar, the fence chip. When the
     editor has focus its own keymap handles the key, so this must not also fire — two handlers for
     one keypress means two saves, and the second one races the first into a 409 conflict. */
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== "s") return;
      const t = e.target as HTMLElement | null;
      if (t?.closest(".cm-editor")) return;        // the editor's keymap owns it
      e.preventDefault();
      void saveRef.current();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    /* Registered ONCE, not per `save` identity. `save` is a useCallback whose dependency list
       includes props that change on every parent render, so keying the listener on it churned the
       subscription continuously — and under StrictMode's double-invoke that left two live
       listeners, so one ⌘S sent two saves and the second raced the first into a 409. The handler
       reads the latest `save` through a ref, so one listener is always enough. */
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  return (
    <section className="editor-surface" aria-label={`Editing ${target.name}`}>
      {/* One bar: identity, breadcrumb, fence, ask menu, reload, Save. It used to be a 128 px header
          above a 40 px editor bar, which put 168 px between the tab strip and the first line of code. */}
      <DocumentBar
        doc={{ id: target.path, kind: target.kind, ref: target.path, name: target.name, rev: 0 }}
        crumbs={crumbsOf(target.path)}
        language={target.language}
        fence={{ label: chip.label, tone: chip.tone, reason: fence.reason }}
        readOnly={readOnly}
        dirty={dirty}
        saving={saving}
        busy={false}
        notice={notice}
        path={target.path}
        onReload={() => onReload?.()}
        onSave={() => void save()}
        onAsk={(a) => onAskAction?.(a)}
        onAttach={() => onAttach?.()}
        onOpenInDatabricks={() => onOpenInDatabricks?.()}
      />

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
            {/* The heading must agree with the reason. Asking "save outside your folder?" over
                "there is no working folder" is a contradiction the user has to resolve. The flag is
                computed where the reason is produced, not sniffed back out of the sentence. */}
            <strong>{asking.noFolder ? "Save without a session?" : "Save outside your working folder?"}</strong>
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
            // One serialization, in the ref, so save and draft read the same bytes the cells mean.
            const serialized = serializeCells(next, target.language);
            text.current = serialized;
            /* The reload after a save hands back the cells we just wrote. Reporting that as an edit
               is what left the buffer permanently dirty — the notice said "saved" while the dot
               said "unsaved", and both were true of different states. Compare by cell content: if
               it is what we saved, we are clean. */
            const saved = savedCells.current;
            const isEcho = !!saved && next.length === saved.length
              && next.every((c, i) => c.kind === saved[i].kind && c.source === saved[i].source);
            if (isEcho) {
              savedCells.current = null;
              setDirty(false);
              return;
            }
            setDirty(true);
            writeDraft({ docId: target.path, text: serialized, basedOn: version.current ?? "", at: Date.now() });
            onCells(next);
          }}
          onAskCell={(cell) => onAskCell?.(cell)}
          onSave={() => void save()}
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
