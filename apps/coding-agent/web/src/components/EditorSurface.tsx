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
import { reconcileIds } from "../domain/reconcile";
import { Markdown } from "./Markdown";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import { askFence, saveDocument, type SaveResult } from "../api/save";
import { runAffordance, runPlan, type CellRun } from "../domain/cellrun";
import { usePythonPolicy } from "../hooks/usePythonPolicy";
import { NotebookBar } from "./NotebookBar";
import { checkCells, parseCells, serializeCells, type Cell } from "../domain/notebook";
import { describeChanges, diffCells, sameCells } from "../domain/changes";
import { checkPath, describeFence } from "../domain/fence";
import { clear as clearDraft, read as readDraft, write as writeDraft } from "../domain/drafts";
import { Editor } from "../editor/Editor";
import { NotebookEditor } from "./NotebookEditor";
import { Clock, Close, Mark, Warning } from "../components/Icons";
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
  onDirtyChange?: (dirty: boolean) => void;
  /** Called with the derived cells on every change, so the parent can render notebook chrome. */
  onCells: (cells: Cell[]) => void;
  /** Ask the agent about one cell: the reason owning the editor is worth building (lens 7).
   *  The index is 1-based, matching what the notebook UI shows and what a binding carries. */
  onAskCell?: (cell: Cell, index: number) => void;
  /** An instruction aimed at one cell, already phrased. `cell` is 1-based; 0 means the whole notebook. */
  onPromptCell?: (p: { cell: number; text: string }) => void;
  /** The bar's actions. The surface does not own "ask the agent"; the app does. */
  onAskAction?: (a: Action) => void;
  /** Copy a link to the document, or to one cell of it (1-based). */
  onCopyLink?: (cell?: number) => void;
  /** The cell a link named (1-based): scrolled into view and marked, without taking keyboard focus. */
  linkedCell?: number | null;
  onAttach?: () => void;
  onOpenInDatabricks?: () => void;
  onReload?: () => void;
}

const SAVE_DEBOUNCE = 150;

export function EditorSurface({
  target, folder, sessionId, source, theme, onSaved, onCells, onAskCell, onPromptCell,
  onAskAction, onAttach, onOpenInDatabricks, onReload, onCopyLink, linkedCell, onDirtyChange,
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
  useEffect(() => { onDirtyChange?.(dirty || restored); }, [dirty, restored, onDirtyChange]);
  /* Cell outputs, keyed by cell id, owned here rather than inside NotebookEditor: a reorder or a
     re-render must not lose a result, and the Save path and the Run path must see the same cells.
     Cleared when the document changes, because another notebook's results are not this one's. */
  const [runs, setRuns] = useState<Record<string, CellRun>>({});
  const running = useRef<Set<string>>(new Set());
  /** A recovery replaces the buffer through the same channel a load uses, because the editor is
   *  uncontrolled: this is the value the Editor is told to show. */
  const [forceValue, setForceValue] = useState<string | null>(null);
  /** Markdown files open RENDERED, because a `.md` file is prose: its headings, links, tables and
   *  formulas are the point, and showing the source by default means every one of them arrives as
   *  syntax (007 MD-7). The bar has a toggle, and `source` is one click away. A file being edited
   *  stays in source: switching the surface under the caret would lose it. */
  const isMarkdown = target.kind === "file" && /\.(md|markdown|mdx)$/i.test(target.path);
  const [preview, setPreview] = useState(isMarkdown);
  useEffect(() => { setPreview(target.kind === "file" && /\.(md|markdown|mdx)$/i.test(target.path)); }, [target.path, target.kind]);

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

  /* Someone else wrote this notebook while it was open: the assistant, or another tab. The server's
     version token changes, and so does `source`. Until now the editor kept the cells it had seeded —
     so the assistant said "I appended a Conclusion cell" over a notebook that still showed one cell,
     and the Reload button did the same. A change we did not make is adopted, and said out loud:
     which cells moved, and one click to put it back. If the user has unsaved edits it is never
     applied over them: they choose. */
  const liveRef = useRef<Cell[]>([]);
  liveRef.current = liveCells;
  const dirtyRef = useRef(false);
  dirtyRef.current = dirty;
  const adoptedVersion = useRef<string | null>(target.version);
  /** The bytes of a plain file we last saved, so its echo is not mistaken for an outside change. */
  const savedFile = useRef<string | null>(null);
  const [agentChange, setAgentChange] = useState<{ before: Cell[]; changed: number[]; summary: string } | null>(null);
  const [incoming, setIncoming] = useState<string | null>(null);
  const [reveal, setReveal] = useState<{ cell: number; n: number } | null>(null);

  const adopt = useCallback((next: string) => {
    const before = liveRef.current;
    // Inherit the identities of the cells that are the same: a new id is a remount, and a remount
    // costs the user their caret, their focus and their scroll position.
    const after = reconcileIds(before, parseCells(next, target.language));
    accepted.current = next;
    text.current = next;
    setLiveCells(after);
    // A result belongs to the code that produced it: keep it for cells that did not change.
    setRuns((prev) => {
      const old = new Map(before.map((c) => [c.id, c.source]));
      return Object.fromEntries(Object.entries(prev).filter(([id]) => {
        const c = after.find((x) => x.id === id);
        return c && old.get(id) === c.source;
      }));
    });
    setDirty(false);
    clearDraft(target.path);
    setIncoming(null);
    onCells(after);
    // Writes in quick succession are ONE change to the reader: keep the first "before", so Undo
    // reverts everything the assistant did since the user last looked, not just the last write.
    setAgentChange((prev) => {
      const base = prev?.before ?? before;
      const d = diffCells(base, after);
      return d.changed.length || d.removed
        ? { before: base, changed: d.changed, summary: describeChanges(d, base.length, after.length) } : null;
    });
  }, [onCells, target.language, target.path]);

  /** Take an outside change to a PLAIN FILE. A notebook has cells and a diff to show; a file is one
   *  buffer, so the change is adopted whole, with the same rules: never over unsaved edits, and only
   *  for a version we did not write ourselves. Without this, a file the agent rewrote stayed frozen
   *  on screen until it was closed and reopened — the same "it never refreshes" complaint, for every
   *  non-notebook document (app.yaml, README.md, a .py next to the notebook). */
  const adoptFile = useCallback((next: string) => {
    accepted.current = next;
    text.current = next;
    setForceValue(next);
    setDirty(false);
    clearDraft(target.path);
    setIncoming(null);
    setNotice({ tone: "ok", text: "updated by the agent" });
  }, [target.path]);

  /** The bytes of this file that are on screen. `text.current` cannot answer that: it is also what
   *  the user has typed, and the load effect above resets it to `source` on every reload — so
   *  comparing the two always said "nothing changed" and a written file never refreshed. */
  const shownSource = useRef(source);
  useEffect(() => {
    if (!source || target.kind !== "file") return;
    if (source === shownSource.current) return;
    shownSource.current = source;
    if (savedFile.current === source) { savedFile.current = null; setDirty(false); return; }  // our own save
    if (dirtyRef.current) { setIncoming(source); return; }
    adoptFile(source);
  }, [source, target.kind, adoptFile]);

  useEffect(() => {
    if (target.kind !== "notebook" || !source || !seeded.current) return;
    if (target.version === adoptedVersion.current) return;
    adoptedVersion.current = target.version;
    const next = parseCells(source, target.language);
    if (savedCells.current && sameCells(next, savedCells.current)) return;   // our own save, coming back
    if (sameCells(next, liveRef.current)) return;
    if (dirtyRef.current) { setIncoming(source); return; }
    adopt(source);
  }, [source, target.version, target.kind, target.language, adopt]);

  const undoAgent = () => {
    if (!agentChange) return;
    const back = reconcileIds(liveRef.current, agentChange.before);
    setAgentChange(null);
    setLiveCells(back);
    text.current = serializeCells(back, target.language);
    onCells(back);
    setDirty(true);
    // `save` reads the latest text through the ref; let the state settle first.
    window.setTimeout(() => saveRef.current(), 0);
  };

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
  /* Not on mount: the seeding effect above has just filled the cells, and clearing them here would
     leave a notebook that has loaded and shows nothing. (This used to be hidden by the first
     `source` being a stale empty one, which re-seeded a moment later.) */
  const shownPath = useRef(target.path);
  useEffect(() => {
    if (shownPath.current === target.path) return;
    shownPath.current = target.path;
    seeded.current = false;
    accepted.current = "";
    setLiveCells([]);
    setRuns({});
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
  // Leaving a tab before the plain-file debounce fires must still preserve the latest bytes.
  // Reordering does not unmount this surface, so it never flushes or reloads the editor.
  useEffect(() => () => {
    window.clearTimeout(saveTimer.current);
    if (dirtyRef.current) writeDraft({ docId: target.path, text: text.current, basedOn: version.current ?? "", at: Date.now() });
  }, [target.path]);

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
    // While the user is mid-edit the draft IS the live buffer, not something to offer back.
    if (draft && draft.text !== source && !dirtyRef.current) setRestored(true);
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
    dirtyRef.current = true;
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
        /* Only if nothing was typed while the request was in flight: a save takes seconds, and
           marking the buffer clean over the user's newer keystrokes would leave Save disabled on
           text that is not on disk. */
        if (text.current === body) setDirty(false);
        // Remember what we wrote, so the reload that follows is recognised as an echo, not an edit.
        savedCells.current = target.kind === "notebook" ? parseCells(body, target.language) : null;
        savedFile.current = target.kind === "file" ? body : null;
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

  const python = usePythonPolicy();
  /** Whatever stops a Python run between polls: Stop in the notebook bar. */
  const stopAll = useRef(false);

  /** Python cells, together: ONE serverless job as the app, so the cells share variables and the cold
   *  start is paid once. `targets` are the cells whose output is wanted; the Python above the last of
   *  them runs too. Every cell asked for ends with a result of its own, never a spinner. */
  const runPython = useCallback(async (targets: Cell[]): Promise<CellRun[]> => {
    const ids = targets.map((c) => c.id).filter((id) => !running.current.has(id));
    if (ids.length === 0) return [];
    ids.forEach((id) => running.current.add(id));
    const waiting = (note: string, seconds = 0): CellRun => ({ state: "running", seconds, error: note, warehouse: "Serverless · as the app" });
    setRuns((r) => ({ ...r, ...Object.fromEntries(ids.map((id) => [id, waiting("starting serverless compute… the first run takes about a minute")])) }));
    const show = ids.map((id) => liveCells.findIndex((c) => c.id === id)).filter((i) => i >= 0);
    const failed = (error: string): CellRun => ({ state: "failed", seconds: 0, error, warehouse: "Serverless · as the app" });
    try {
      const results = await api.runPython(
        liveCells.map((c) => ({ language: c.kind === "markdown" ? "markdown" : c.language || target.language, source: c.source })),
        show,
        { stop: () => stopAll.current,
          onStage: (stage, seconds) => setRuns((r) => ({ ...r, ...Object.fromEntries(
            ids.filter((id) => r[id]?.state === "running").map((id) => [id, waiting(`${stage}… ${Math.round(seconds)}s`, seconds)])) })) });
      const out = ids.map((id) => results[String(liveCells.findIndex((c) => c.id === id))]
        ?? failed("the run ended without a result for this cell"));
      setRuns((r) => ({ ...r, ...Object.fromEntries(ids.map((id, n) => [id, out[n]])) }));
      return out;
    } catch (e) {
      const why = failed(e instanceof Error ? e.message : "the request did not reach the app");
      setRuns((r) => ({ ...r, ...Object.fromEntries(ids.map((id) => [id, why])) }));
      return ids.map(() => why);
    } finally {
      ids.forEach((id) => running.current.delete(id));
    }
  }, [liveCells, target.language]);

  /** Run one cell. The result is a value, so every outcome renders from one place. */
  const runCell = useCallback(async (cell: Cell): Promise<CellRun | null> => {
    if (running.current.has(cell.id)) return null;
    const how = runAffordance(cell.kind === "markdown" ? "markdown" : cell.language || target.language, cell.source, python);
    if (how.engine === "python") { stopAll.current = false; return (await runPython([cell]))[0] ?? null; }
    running.current.add(cell.id);
    const key = cell.id;
    setRuns((r) => ({ ...r, [key]: { state: "running", seconds: 0 } }));
    try {
      const result = await api.runCell(cell.language || target.language, cell.source);
      setRuns((r) => ({ ...r, [key]: result }));
      return result;
    } catch (e) {
      const failed: CellRun = { state: "failed", seconds: 0,
        error: e instanceof Error ? e.message : "the request did not reach the app" };
      setRuns((r) => ({ ...r, [key]: failed }));
      return failed;
    } finally {
      running.current.delete(cell.id);
    }
  }, [target.language, python, runPython]);

  /* Run a list of cells, in order, stopping at the first failure. Sequential on purpose: a later cell
     may read what an earlier one made, and a failure that is not the first one is noise. `stopAll`
     is a ref so Stop takes effect between cells without re-rendering the loop. Run all clears every
     output first; a span clears only the cells it is about to run. */
  const [runningAll, setRunningAll] = useState(false);
  const [batch, setBatch] = useState<string[] | null>(null);
  const plan = useMemo(() => runPlan(liveCells, python), [liveCells, python]);
  const runIds = useCallback(async (ids: string[], clearAllOutputs = false) => {
    if (runningAll || ids.length === 0) return;
    const snapshot = liveCells;
    stopAll.current = false;
    setRunningAll(true);
    setBatch(ids);
    if (clearAllOutputs) setRuns({});
    else setRuns((r) => {
      const next = { ...r };
      ids.forEach((id) => { delete next[id]; });
      return next;
    });
    try {
      const pyIds = ids.filter((id) => {
        const cell = snapshot.find((c) => c.id === id);
        if (!cell) return false;
        return runAffordance(cell.kind === "markdown" ? "markdown" : cell.language || target.language, cell.source, python).engine === "python";
      });
      // The Python cells are one job, started now and read at the end, while the SQL cells run in
      // order on the warehouse. They are different engines, so neither waits for the other; SQL still
      // stops at its first failure, and a Python failure is reported on its own cell.
      const pythonRun = pyIds.length ? runPython(snapshot.filter((c) => pyIds.includes(c.id))) : Promise.resolve([]);
      for (const id of ids) {
        if (stopAll.current) break;
        if (pyIds.includes(id)) continue;
        const cell = snapshot.find((c) => c.id === id);
        if (!cell) continue;
        const result = await runCell(cell);
        if (result && result.state !== "succeeded") break;
      }
      await pythonRun;
    } finally {
      setRunningAll(false);
      setBatch(null);
    }
  }, [liveCells, runCell, runPython, runningAll, python, target.language]);
  const runAll = useCallback(async () => {
    const ids = runPlan(liveCells, python).runnable;
    await runIds(ids, true);
  }, [liveCells, python, runIds]);

  const clearAllRuns = useCallback(() => setRuns({}), []);
  const clearRun = useCallback((cell: Cell) => {
    setRuns((r) => {
      const next = { ...r };
      delete next[cell.id];
      return next;
    });
  }, []);

  const restore = () => {
    const draft = readDraft(target.path);
    if (!draft) return;
    text.current = draft.text;
    setDirty(true);
    setRestored(false);
    setForceValue(draft.text);
    if (target.kind === "notebook" && onCells) onCells(parseCells(draft.text, target.language));
    /* A restored draft is the buffer now. Clearing it the next tick hands the editor back to `source`,
       which still holds the draft's text, so nothing visibly changes — but the one-shot override no
       longer outranks every later adoption of an outside change. */
    window.setTimeout(() => setForceValue(null), 0);
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
    <section className="editor-surface" aria-label={`Editing ${target.name}`}
      /* A button must not steal the caret. Clicking Save, Undo, Run or Allow once while typing leaves
         the cursor where it was (mousedown's default is what moves focus; a programmatic focus, like
         opening a prompt, still works). Fields keep their normal behaviour. */
      onMouseDown={(e) => {
        const t = e.target as HTMLElement;
        if (t.closest("button, [role=button]") && !t.closest("input, textarea, select, [contenteditable=true]")
          && document.activeElement?.closest(".cm-editor, .cell-block")) e.preventDefault();
      }}>
      {/* One bar: identity, breadcrumb, fence, ask menu, reload, Save. It used to be a 128 px header
          above a 40 px editor bar, which put 168 px between the tab strip and the first line of code. */}
      <DocumentBar
        doc={{ id: target.path, kind: target.kind, ref: target.path, name: target.name, rev: 0 }}
        crumbs={crumbsOf(target.path)}
        language={target.language}
        fence={{ label: chip.label, tone: chip.tone, reason: effective.reason || "Saving in this folder is allowed" }}
        readOnly={readOnly}
        dirty={dirty}
        saving={saving}
        busy={false}
        notice={notice}
        path={target.path}
        onReload={() => onReload?.()}
        onSave={() => void save()}
        onAsk={(a) => onAskAction?.(a)}
        onCopyLink={() => onCopyLink?.()}
        onAttach={() => onAttach?.()}
        onOpenInDatabricks={() => onOpenInDatabricks?.()}
        preview={isMarkdown ? { on: preview, onToggle: () => setPreview((v) => !v) } : undefined}
      />

      {agentChange && (
        <div className="draft-banner agent-banner" role="status">
          <Mark size={14} />
          <span><strong>This notebook was updated</strong> · {agentChange.summary}</span>
          <button className="btn sm" onClick={() => setReveal((r) => ({ cell: agentChange.changed[0] ?? 1, n: (r?.n ?? 0) + 1 }))}>Show</button>
          <button className="btn sm" onClick={undoAgent}>Undo</button>
          <button className="btn ghost sm" aria-label="Dismiss" onClick={() => setAgentChange(null)}><Close size={12} /></button>
        </div>
      )}

      {incoming && (
        <div className="ask-banner" role="alertdialog" aria-label="The notebook changed">
          <Warning size={15} />
          <div>
            <strong>This notebook changed while you have unsaved edits</strong>
            <p>Take the new version and your edits are replaced, or keep yours and your next save overwrites it.</p>
          </div>
          <button className="btn primary sm" onClick={() => adopt(incoming)}>Take the new version</button>
          <button className="btn ghost sm" onClick={() => setIncoming(null)}>Keep mine</button>
        </div>
      )}

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
      {target.kind === "notebook" && !readOnly && liveCells.length > 0 && (
        <NotebookBar plan={plan} runs={runs} runningAll={runningAll} batch={batch}
          onRunAll={() => void runAll()} onStop={() => { stopAll.current = true; }} onClear={clearAllRuns} />
      )}

      {target.kind === "notebook" ? (
        <NotebookEditor
          cells={liveCells}
          language={target.language}
          theme={theme}
          readOnly={readOnly}
          python={python}
          linkedCell={linkedCell ?? null}
          changedCells={agentChange?.changed}
          viewKey={target.path}
          reveal={reveal}
          onCopyCellLink={onCopyLink ? (n) => onCopyLink(n) : undefined}
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
          onAskCell={(cell, index) => onAskCell?.(cell, index)}
          onPrompt={onPromptCell}
          onSave={() => void save()}
          runs={runs}
          onRunCell={(cell) => void runCell(cell)}
          onRunCells={(ids) => void runIds(ids)}
          onClearOutputs={clearAllRuns}
          onStopRun={() => { stopAll.current = true; }}
          batch={batch}
          onClearRun={clearRun}
        />
      ) : isMarkdown && preview ? (
        <div className="md-preview" aria-label={`${target.name}, rendered`}>
          <Markdown text={forceValue ?? text.current ?? source} />
          {dirty && (
            <p className="md-preview-note" role="status">
              You have unsaved changes. <button className="btn ghost sm" onClick={() => setPreview(false)}>Show the source</button>
            </p>
          )}
        </div>
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
