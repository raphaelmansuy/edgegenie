/** Notebook mode: a stack of cells, each an independent editor.
 *
 * This is the same model JupyterLab uses (a list of independent CodeMirror states, not one editor
 * pretending to be cells), which is what makes per-cell focus, per-cell actions and a cell-level
 * diff possible without fighting the editor.
 *
 * The one interaction that makes a notebook feel like a notebook: a **markdown cell renders when
 * you are not in it, and edits when you are** (NB-3). Getting that right without the text changing
 * is the detail users notice.
 */
import { Fragment, useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react";
import {
  insertCell, mergeWithNext, moveCell, newCell, removeCell, setCellKind, splitCell, updateCellSource, type Cell,
} from "../domain/notebook";
import { ChevronDown, ChevronRight, Close, LinkIcon, Play, Plus, Sparkle } from "./Icons";
import { CellInsert } from "./CellInsert";
import { CellPrompt } from "./CellPrompt";
import { editPrompt, fixPrompt, insertPrompt } from "../domain/cellprompt";
import { runAffordance, spanIds, type CellRun, type PythonPolicy } from "../domain/cellrun";
import { CellOutput } from "./CellOutput";
import { Editor } from "../editor/Editor";
import { Markdown } from "./Markdown";
import { MarkdownToolbar } from "./MarkdownToolbar";
import { parseMarkdown, type MarkdownModel } from "../domain/markdown/parse";
import { headingId } from "../domain/markdown/policy";
import { readingState, transition } from "../domain/markdown/viewstate";
import { commandKey, OPEN_SHORTCUTS, type Advance, type CellCommand, type RunSpan } from "../domain/cellkeys";
import { executionMap } from "../domain/minimap";
import { Minimap } from "./Minimap";
import { clampTo, recall, remember, type ViewState } from "../domain/viewstate";
import type { EditorChord, EditorHost } from "../editor/host";
import { display } from "../domain/keys";

/** A request to move the user's place: into a cell's text ("edit") or onto the cell itself
 *  ("command"). `n` makes each request distinct. See Editor's `focusRequest`. */
type Req = { id: string; mode: "edit" | "command"; at?: number; n: number };
// Weak keys follow the immutable cell source model and cannot retain closed notebooks.
const markdownModels = new WeakMap<Cell, MarkdownModel>();
function modelOf(cell: Cell) {
  let model = markdownModels.get(cell);
  if (!model) { model = parseMarkdown(cell.source); markdownModels.set(cell, model); }
  return model;
}

/** The element that scrolls the cell stack: the stack itself (it owns its overflow) or an ancestor. */
function scrollParent(el: HTMLElement | null): HTMLElement | null {
  for (let n: HTMLElement | null = el; n; n = n.parentElement) {
    const o = getComputedStyle(n).overflowY;
    if (o === "auto" || o === "scroll") return n;
  }
  return null;
}

interface Props {
  cells: Cell[];
  language: string;
  theme: "light" | "dark";
  readOnly?: boolean;
  onChange: (cells: Cell[]) => void;
  /** Ask the agent about one cell: the reason owning the editor is worth it (spec 003 lens 7). */
  onAskCell?: (cell: Cell, index: number) => void;
  /** Send an instruction about one cell (`index` is 0-based) or ask for a new one after `after` cells.
   *  The text is already a full prompt; the app only has to bind it to the cell and send it. */
  onPrompt?: (p: { cell: number; text: string }) => void;
  /** ⌘S pressed inside a cell. It must reach the document's save, not stop at the cell. */
  onSave?: () => void;
  /** Per-cell run state, keyed by cell id. Owned by the surface, so a reorder keeps the result. */
  runs?: Record<string, CellRun>;
  /** Run one cell. Absent when the document cannot be run (spec 006 X1). */
  onRunCell?: (cell: Cell, index: number) => void;
  onClearRun?: (cell: Cell) => void;
  /** A result table was switched to a chart, or the chart changed. */
  onRunView?: (cell: Cell, table: number, view: import("../domain/chart").TableView) => void;
  /** The cell a link named (1-based). It is scrolled to and marked; keyboard focus is left alone. */
  linkedCell?: number | null;
  /** 1-based cells another writer just changed: marked until the user dismisses the banner. */
  changedCells?: number[];
  /** Whether Python cells may run (the server's answer), so the Run control says what it will do. */
  python?: PythonPolicy;
  /** Run these cells, in order, stopping at the first failure. Run all, above, below, and a multi-selection. */
  onRunCells?: (ids: string[]) => void;
  onClearOutputs?: () => void;
  onStopRun?: () => void;
  /** Cells a batch run is walking right now, so the map can mark the ones still queued. */
  batch?: string[] | null;
  /** Copy a link to one cell (1-based). */
  onCopyCellLink?: (cell: number) => void;
  /** Identifies the document, so the user's place (cell, caret, scroll) is remembered per document
   *  and restored when it is reopened, reloaded or comes back after a tab switch. */
  viewKey?: string;
  /** Scroll a cell into view because the USER asked (the banner's Show). Never set by a data update:
   *  the page must not move on its own while someone is reading or the assistant is writing. */
  reveal?: { cell: number; n: number } | null;
}

export function NotebookEditor({
  cells, language, theme, readOnly = false, onChange, onAskCell, onPrompt, onSave, runs, onRunCell, onClearRun, onRunView,
  linkedCell = null, changedCells, onCopyCellLink, python, viewKey, reveal,
  onRunCells, onClearOutputs, onStopRun, batch = null,
}: Props) {
  const root = useRef<HTMLDivElement>(null);
  const [outlineOpen, setOutlineOpen] = useState(false);
  const headings = useMemo(() => cells.flatMap(cell => cell.kind === "markdown" ? modelOf(cell).headings.map(h => ({ ...h, cellId: cell.id })) : []), [cells]);
  const runnable = useMemo(() => spanIds(cells, python, 0, "all"), [cells, python]);
  const runnableSet = useMemo(() => new Set(runnable), [runnable]);
  const runnableCounts = useMemo(() => { const out = [0]; for (const c of cells) out.push(out.at(-1)! + Number(runnableSet.has(c.id))); return out; }, [cells, runnableSet]);
  /* A link to a cell must land ON the cell: scroll it to the middle and mark it. Runs when the link
     changes or when the cells first exist (a link is opened before the notebook has loaded). */
  /* Cells another writer just changed are marked, never scrolled to. Moving the page on its own is the
     one thing a reader of a live document cannot forgive: the banner's Show button brings them into
     view when the user wants. A class, not a prop through CellBlock: it is a transient mark, owned by
     the banner that announces it. */
  useEffect(() => {
    if (!changedCells?.length) return;
    const nodes = changedCells.map((n) => root.current?.querySelector<HTMLElement>(`[data-cell="${n}"]`)).filter(Boolean) as HTMLElement[];
    nodes.forEach((el) => el.classList.add("is-agent-changed"));
    return () => nodes.forEach((el) => el.classList.remove("is-agent-changed"));
  }, [changedCells, cells.length]);
  useEffect(() => {
    if (!reveal) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    root.current?.querySelector(`[data-cell="${reveal.cell}"]`)
      ?.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reveal?.n]);
  const target = linkedCell && cells[linkedCell - 1] ? cells[linkedCell - 1].id : null;
  useEffect(() => {
    if (!target || !linkedCell) return;
    setFocused(target);
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    root.current?.querySelector(`[data-cell="${linkedCell}"]`)
      ?.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, linkedCell]);
  /** One prompt open at a time: on a cell (edit) or in a seam (insert, `after` cells above it). */
  const [prompt, setPrompt] = useState<{ mode: "edit"; id: string } | { mode: "insert"; after: number } | null>(null);
  const [focused, setFocused] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const set = useCallback((next: Cell[]) => onChange(next), [onChange]);
  const cellsRef = useRef(cells);
  cellsRef.current = cells;

  /* ---- the user's place -------------------------------------------------------------------- */
  const [req, setReq] = useState<Req | null>(null);
  const reqSeq = useRef(0);
  const request = (id: string, mode: Req["mode"], at?: number) => {
    const n = (reqSeq.current += 1);
    setReq({ id, mode, at, n });
    // A request that nobody honoured (its cell is collapsed or gone) must not fire on a later mount.
    window.setTimeout(() => setReq((r) => (r?.n === n ? null : r)), 2500);
  };
  const done = useCallback((n: number) => setReq((r) => (r?.n === n ? null : r)), []);
  const carets = useRef(new Map<string, number>());
  const armed = useRef("");
  const [selected, setSelected] = useState<string[]>([]);
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  const anchor = useRef(0);
  const clip = useRef<Cell[]>([]);
  const [hiddenOut, setHiddenOut] = useState<Set<string>>(new Set());
  /** Snapshots before each structural change, for `z`. Text typing is CodeMirror's own undo. */
  const undo = useRef<Cell[][]>([]);

  const pending = useRef<Partial<ViewState>>({});
  const flushTimer = useRef<number | undefined>(undefined);
  const flush = useCallback(() => {
    window.clearTimeout(flushTimer.current);
    if (viewKey && Object.keys(pending.current).length) remember(viewKey, pending.current);
    pending.current = {};
  }, [viewKey]);
  const note = useCallback((patch: Partial<ViewState>) => {
    if (!viewKey) return;
    pending.current = { ...pending.current, ...patch };
    window.clearTimeout(flushTimer.current);
    flushTimer.current = window.setTimeout(flush, 150);
  }, [viewKey, flush]);
  useEffect(() => flush, [flush]);                       // leaving a document saves its place

  // Remember how far down the user is, and restore it when the document comes back.
  useEffect(() => {
    const sp = scrollParent(root.current);
    if (!viewKey || !sp) return;
    const onScroll = () => note({ scroll: sp.scrollTop });
    sp.addEventListener("scroll", onScroll, { passive: true });
    return () => sp.removeEventListener("scroll", onScroll);
  }, [viewKey, note]);
  const restored = useRef<string | null>(null);
  useEffect(() => {
    if (!viewKey || restored.current === viewKey || cells.length === 0) return;
    restored.current = viewKey;
    const saved = recall(viewKey);
    if (!saved || linkedCell) return;                    // a link to a cell outranks the old place
    const st = clampTo(saved, cells.length, (n) => cells[n - 1]?.source.length ?? 0);
    const sp = scrollParent(root.current);
    let moved = false;
    const stop = () => { moved = true; };
    sp?.addEventListener("wheel", stop, { passive: true, once: true });
    sp?.addEventListener("pointerdown", stop, { once: true });
    const place = () => { if (sp && !moved) sp.scrollTop = st.scroll; };
    // Editors load lazily and settle the layout a moment after mount; re-apply until the user moves.
    const timers = [0, 120, 400].map((ms) => window.setTimeout(place, ms));
    const target = st.cell > 0 ? cells[st.cell - 1] : null;
    const idle = !document.activeElement || document.activeElement === document.body;
    if (target && idle) request(target.id, st.mode, st.mode === "edit" ? st.caret : undefined);
    return () => timers.forEach(window.clearTimeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewKey, cells.length]);

  /* ---- structure ---------------------------------------------------------------------------- */
  const commit = (next: Cell[]) => {
    undo.current = [...undo.current.slice(-49), cellsRef.current];
    set(next);
  };

  const addAt = (at: number, kind: "code" | "markdown") => {
    const cell = newCell(kind, language);
    commit(insertCell(cells, at, cell));
    request(cell.id, "edit");
  };

  const undoStructure = () => {
    const prev = undo.current.pop();
    if (!prev) return;
    // Restore the shape (which cells, in what order and kind) but keep the text as it is now: undoing
    // a delete must never throw away what was typed since.
    const now = new Map(cellsRef.current.map((c) => [c.id, c]));
    set(prev.map((c) => (now.has(c.id) ? { ...c, source: now.get(c.id)!.source } : c)));
    // Select what the undo brought back (the restored cell), else where the user was.
    const back = prev.find((c) => !now.has(c.id));
    const keep = back?.id ?? (focused && prev.some((c) => c.id === focused) ? focused : prev[0]?.id);
    if (keep) request(keep, "command");
  };

  const selectTo = (index: number, extend: boolean) => {
    const list = cellsRef.current;
    const t = list[Math.max(0, Math.min(list.length - 1, index))];
    if (!t) return;
    if (!extend) {
      anchor.current = list.indexOf(t);
      setSelected([t.id]);
    } else {
      const a = Math.max(0, Math.min(anchor.current, list.length - 1));
      const b = list.indexOf(t);
      const [lo, hi] = a < b ? [a, b] : [b, a];
      setSelected(list.slice(lo, hi + 1).map((c) => c.id));
    }
    request(t.id, "command");
  };

  const runSpan = (span: "all" | "above" | "below" | "these", index: number, these: string[] = []) => {
    const ids = spanIds(cellsRef.current, python, index, span, these);
    if (ids.length) onRunCells?.(ids);
  };

  const toggleOutput = (id: string) => {
    setHiddenOut((cur) => {
      const next = new Set(cur);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  const dropCells = (ids: string[], fromIndex: number) => {
    const next = cellsRef.current.filter((c) => !ids.includes(c.id));
    commit(next);
    const t = next[Math.min(fromIndex, next.length - 1)];
    setSelected(t ? [t.id] : []);
    if (t) request(t.id, "command"); else setFocused(null);
  };

  const onClipboard = (op: "copy" | "cut" | "paste", i: number) => {
    const list = cellsRef.current;
    const ids = selectedRef.current.length ? selectedRef.current : [list[i]?.id].filter(Boolean) as string[];
    const picked = list.filter((c) => ids.includes(c.id));
    if (op === "copy" || op === "cut") {
      if (!picked.length) return;
      clip.current = picked.map((c) => ({ ...c }));
      if (op === "cut" && !readOnly) dropCells(picked.map((c) => c.id), i);
      return;
    }
    if (readOnly || !clip.current.length) return;
    let next = list;
    let at = i + 1;
    const clones = clip.current.map((c) => newCell(c.kind, c.kind === "markdown" ? "markdown" : c.language, c.source));
    for (const c of clones) {
      next = insertCell(next, at, c);
      at += 1;
    }
    commit(next);
    setSelected(clones.map((c) => c.id));
    request(clones[0].id, "command");
  };

  const runCell = (i: number, advance: Advance, from: "edit" | "command") => {
    const cell = cells[i];
    if (!cell) return;
    const many = selectedRef.current.length > 1 && selectedRef.current.includes(cell.id);
    if (many && advance === "stay" && onRunCells) runSpan("these", i, selectedRef.current);
    else if (cell.kind === "code" && !readOnly && onRunCell
      && runAffordance(cell.language || "python", cell.source, python).enabled) onRunCell(cell, i);
    if (advance === "stay") {
      if (cell.kind === "markdown" || from === "command") request(cell.id, "command");
    } else if (advance === "next") {
      const t = cells[i + 1];
      if (t) request(t.id, from === "edit" && t.kind === "code" && !readOnly ? "edit" : "command");
      else if (!readOnly) addAt(cells.length, "code");   // Shift+Enter on the last cell adds a cell
    } else if (!readOnly) addAt(i + 1, "code");
  };

  const runCommand = (cmd: CellCommand, i: number) => {
    const cell = cells[i];
    if (!cell) return;
    switch (cmd.type) {
      case "select": {
        const to = cmd.to === "prev" ? i - 1 : cmd.to === "next" ? i + 1 : cmd.to === "first" ? 0 : cells.length - 1;
        selectTo(to, Boolean(cmd.extend));
        break;
      }
      case "selectAll": setSelected(cells.map((c) => c.id)); anchor.current = 0; break;
      case "edit": request(cell.id, "edit", carets.current.get(cell.id) ?? Infinity); break;
      case "insert": if (!readOnly) addAt(cmd.where === "above" ? i : i + 1, "code"); break;
      case "delete": {
        if (readOnly) break;
        const ids = selectedRef.current.includes(cell.id) && selectedRef.current.length > 1
          ? selectedRef.current : [cell.id];
        dropCells(ids, i);
        break;
      }
      case "convert":
        if (!readOnly && cell.kind !== cmd.kind) { commit(setCellKind(cells, cell.id, cmd.kind, language)); request(cell.id, "command"); }
        break;
      case "move": {
        const to = i + cmd.by;
        if (!readOnly && to >= 0 && to < cells.length) { commit(moveCell(cells, i, to)); request(cell.id, "command"); }
        break;
      }
      case "undo": if (!readOnly) undoStructure(); break;
      case "run": runCell(i, cmd.advance, "command"); break;
      case "runSpan": runSpan(cmd.span, i); break;
      case "ask": if (onPrompt) setPrompt({ mode: "edit", id: cell.id }); break;
      case "output": toggleOutput(cell.id); break;
      case "merge": if (!readOnly) { commit(mergeWithNext(cells, i)); request(cell.id, "command"); } break;
      case "split": {
        if (readOnly) break;
        const next = splitCell(cells, i, carets.current.get(cell.id) ?? cell.source.length);
        if (next !== cells && next.length !== cells.length) {
          commit(next);
          const born = next[i + 1];
          if (born) request(born.id, "edit", 0);
        }
        break;
      }
      case "clipboard": onClipboard(cmd.op, i); break;
      case "clearOutputs": onClearOutputs?.(); break;
      case "stop": onStopRun?.(); break;
      case "shortcuts": window.dispatchEvent(new Event(OPEN_SHORTCUTS)); break;
      case "scroll": {
        const sp = scrollParent(root.current);
        if (sp) sp.scrollBy({ top: cmd.by * Math.max(120, sp.clientHeight * 0.8) });
        break;
      }
    }
  };

  const onChord = (i: number, chord: EditorChord): boolean => {
    if (chord === "escape") { request(cells[i].id, "command"); return true; }
    if (chord === "run-all" || chord === "run-above" || chord === "run-below") {
      const span: RunSpan = chord === "run-all" ? "all" : chord === "run-above" ? "above" : "below";
      runSpan(span, i);
      return true;
    }
    if (chord === "split") { runCommand({ type: "split" }, i); return true; }
    runCell(i, chord === "run-next" ? "next" : chord === "run-insert" ? "insert" : "stay", "edit");
    return true;
  };

  // Keyboard model for the cell stack (NB-2): see domain/cellkeys.ts. The cell itself (not its text)
  // being focused IS command mode.
  const onKey = (e: React.KeyboardEvent) => {
    /* ⌘⇧I / Ctrl+⇧I: ask about the cell you are in (007 KB-10). It moved off ⌘I because the shortcut
       sheet promised ⌘I to the inspector, and a chord with two meanings is the bug this spec exists
       for. Note the shift: `toLowerCase()` would also match ⌘I, so the modifier is checked first. */
    if ((e.metaKey || e.ctrlKey) && e.shiftKey && !e.altKey && e.key.toLowerCase() === "i" && focused && onPrompt) {
      e.preventDefault();
      setPrompt({ mode: "edit", id: focused });
      return;
    }
    const t = e.target as HTMLElement;
    if (!t.classList.contains("cell-block")) return;
    const { command, armed: next } = commandKey(e, armed.current);
    armed.current = next;
    if (!command) return;
    e.preventDefault();
    runCommand(command, Number(t.dataset.cell) - 1);
  };

  const seam = (after: number) => (
    prompt?.mode === "insert" && prompt.after === after ? (
      <CellPrompt key={`prompt-${after}`} mode="insert"
        label={after <= 0 ? "at the top" : `after cell ${after}`}
        onClose={() => setPrompt(null)}
        onSend={(text) => { setPrompt(null); onPrompt?.({ cell: after, text: insertPrompt(after, text) }); }} />
    ) : (
      <CellInsert key={`seam-${after}`} after={after} total={cells.length} always={after === cells.length}
        onCode={() => addAt(after, "code")} onText={() => addAt(after, "markdown")}
        onAgent={onPrompt ? () => setPrompt({ mode: "insert", after }) : undefined} />
    )
  );

  const map = executionMap(cells, runs ?? {}, runnable, batch);

  return (
    <div className="nb-stage">
    <div className="nb-markdown-navigation" onKeyDown={e => { if (e.key === "Escape") { setOutlineOpen(false); e.stopPropagation(); } }}>
      <button type="button" className="btn sm" aria-expanded={outlineOpen} onClick={() => setOutlineOpen(v => !v)}>Outline</button>
      {outlineOpen && <nav className="nb-markdown-outline" aria-label="Notebook headings">
        <strong>Notebook outline</strong>
        {!headings.length && <p>No Markdown headings yet.</p>}
        {headings.map(h => <button type="button" key={`${h.cellId}-${h.ordinal}`} style={{ paddingInlineStart: 12 + (h.depth - 1) * 12 }} onClick={() => {
          setCollapsed(previous => { const next = new Set(previous); next.delete(h.cellId); return next; });
          const node = document.getElementById(headingId(`${viewKey || "notebook"}:${h.cellId}`, h.ordinal));
          if (node) { node.scrollIntoView({ block: "start" }); node.focus({ preventScroll: true }); }
          else { request(h.cellId, "command"); window.setTimeout(() => document.getElementById(headingId(`${viewKey || "notebook"}:${h.cellId}`, h.ordinal))?.scrollIntoView({ block: "start" }), 0); }
          setOutlineOpen(false);
        }}>{h.label || "Untitled heading"}</button>)}
      </nav>}
    </div>
    <div className="cells" ref={root} onKeyDown={onKey}>
      {cells.length === 0 && !readOnly && seam(0)}
      {cells.map((cell, i) => (
        <Fragment key={cell.id}>
        <CellBlock
          cell={cell}
          markdownModel={cell.kind === "markdown" ? modelOf(cell) : undefined}
          index={i}
          total={cells.length}
          language={language}
          theme={theme}
          readOnly={readOnly}
          documentPath={viewKey || ""}
          focused={focused === cell.id}
          selected={selected.length > 1 && selected.includes(cell.id)}
          collapsed={collapsed.has(cell.id)}
          outputHidden={hiddenOut.has(cell.id)}
          onToggleOutput={() => toggleOutput(cell.id)}
          onRunSpan={(span) => runSpan(span, i)}
          onFocus={(mode) => {
            setFocused(cell.id);
            note({ cell: i + 1, mode, caret: mode === "edit" ? carets.current.get(cell.id) ?? 0 : 0 });
          }}
          onBlur={() => setFocused((f) => (f === cell.id ? null : f))}
          request={req?.id === cell.id ? req : null}
          onRequestDone={done}
          onCaret={(pos) => { carets.current.set(cell.id, pos); note({ cell: i + 1, caret: pos, mode: "edit" }); }}
          onChord={(chord) => onChord(i, chord)}
          onEdit={() => request(cell.id, "edit", carets.current.get(cell.id) ?? 0)}
          onToggleCollapse={() => {
            const next = new Set(collapsed);
            if (next.has(cell.id)) next.delete(cell.id);
            else next.add(cell.id);
            setCollapsed(next);
          }}
          onSource={(src) => set(updateCellSource(cells, cell.id, src))}
          onMove={(to) => { commit(moveCell(cells, i, to)); request(cell.id, "command"); }}
          onDelete={() => {
            const next = removeCell(cells, cell.id);
            commit(next);
            const t = next[Math.min(i, next.length - 1)];
            if (t) request(t.id, "command"); else setFocused(null);
          }}
          onConvert={(kind) => commit(setCellKind(cells, cell.id, kind, language))}
          onInsertAfter={(kind) => addAt(i + 1, kind)}
          onAsk={() => (onPrompt ? setPrompt({ mode: "edit", id: cell.id }) : onAskCell?.(cell, i))}
          prompting={prompt?.mode === "edit" && prompt.id === cell.id}
          onClosePrompt={() => setPrompt(null)}
          onDiscuss={onAskCell ? () => { setPrompt(null); onAskCell(cell, i); } : undefined}
          onPromptSend={(instruction) => {
            setPrompt(null);
            onPrompt?.({ cell: i + 1, text: editPrompt(i + 1, instruction) });
          }}
          onFix={onPrompt ? (error) => onPrompt({ cell: i + 1, text: fixPrompt(i + 1, error) }) : undefined}
          onSave={() => onSave?.()}
          run={runs?.[cell.id]}
          canRun={Boolean(onRunCell)}
          onRun={() => onRunCell?.(cell, i)}
          aboveEnabled={runnableCounts[i] > 0}
          belowEnabled={runnableCounts[cells.length] - runnableCounts[i] > 0}
          onSelectClick={(e) => {
            if (e.shiftKey) selectTo(i, true);
            else if (e.metaKey || e.ctrlKey) {
              anchor.current = i;
              setSelected((cur) => (cur.includes(cell.id) ? cur.filter((id) => id !== cell.id) : [...cur, cell.id]));
            }
          }}
          onClearRun={() => onClearRun?.(cell)}
          onRunView={onRunView ? (table, view) => onRunView(cell, table, view) : undefined}
          onCopyLink={onCopyCellLink ? () => onCopyCellLink(i + 1) : undefined}
          python={python}
        />
        {!readOnly && (i < cells.length - 1 || prompt?.mode === "insert" && prompt.after === cells.length) && seam(i + 1)}
        </Fragment>
      ))}
      {!readOnly && cells.length > 0 && seam(cells.length)}
    </div>
    <Minimap map={map} onJump={(n) => { const c = cellsRef.current[n - 1]; if (c) request(c.id, "command"); }} />
    </div>
  );
}

interface CellProps {
  markdownModel?: MarkdownModel;
  documentPath: string;
  cell: Cell;
  index: number;
  total: number;
  language: string;
  theme: "light" | "dark";
  readOnly: boolean;
  focused: boolean;
  selected: boolean;
  collapsed: boolean;
  outputHidden: boolean;
  onToggleOutput: () => void;
  onRunSpan: (span: "above" | "below") => void;
  onFocus: (mode: "edit" | "command") => void;
  onBlur: () => void;
  request: Req | null;
  onRequestDone: (n: number) => void;
  onCaret: (pos: number) => void;
  onChord: (chord: EditorChord) => boolean;
  onEdit: () => void;
  onToggleCollapse: () => void;
  onSource: (s: string) => void;
  onMove: (to: number) => void;
  onDelete: () => void;
  onConvert: (kind: "code" | "markdown") => void;
  onInsertAfter: (kind: "code" | "markdown") => void;
  onAsk: () => void;
  prompting: boolean;
  onClosePrompt: () => void;
  onDiscuss?: () => void;
  onPromptSend: (instruction: string) => void;
  onFix?: (error: string) => void;
  onSave: () => void;
  run?: CellRun;
  canRun: boolean;
  onRun: () => void;
  aboveEnabled: boolean;
  belowEnabled: boolean;
  onSelectClick: (e: React.MouseEvent) => void;
  onClearRun: () => void;
  onRunView?: (table: number, view: import("../domain/chart").TableView) => void;
  onCopyLink?: () => void;
  python?: PythonPolicy;
}

function CellBlock(p: CellProps) {
  const { cell, index, theme, readOnly, focused, collapsed, selected } = p;
  const isMd = cell.kind === "markdown";
  const [runMenu, setRunMenu] = useState(false);
  /** A markdown cell shows prose until you enter it. Entering is a click or Enter on the block. */
  const [view, dispatchView] = useReducer(transition, { ...readingState, readOnly });
  const editing = isMd ? view.mode === "edit" : true;
  const setEditing = (value: boolean) => dispatchView({ type: value ? "edit" : "preview" });
  useEffect(() => { dispatchView({ type: "permission", readOnly }); }, [readOnly]);
  // Explicit insertion requests enter edit mode; loaded empty cells remain readable.
  const wantsEdit = !isMd || editing && !readOnly;
  const editorHost = useRef<EditorHost | null>(null);
  const retainedState = useRef<{ value: string; state: unknown } | null>(null);
  const composing = useRef(false);
  useEffect(() => { if (collapsed) dispatchView({ type: "preview" }); }, [collapsed]);
  const [hostReady, setHostReady] = useState(false);
  const preview = () => {
    if (composing.current) { dispatchView({ type: "preview" }); return; }
    const value = editorHost.current?.getValue();
    if (editing && value !== undefined && value !== cell.source) p.onSource(value);
    setEditing(false); section.current?.focus({ preventScroll: true });
  };
  // Whether this cell CAN run is a domain decision, so the control cannot claim something the server
  // will refuse (006 X1, 00 P4). A disabled button with the reason in its title beats a lying one.
  const affordance = runAffordance(isMd ? "markdown" : cell.language || "python", cell.source, p.python);

  const section = useRef<HTMLElement>(null);
  useEffect(() => {
    if (!runMenu) return;
    const close = (e: MouseEvent) => {
      if (!section.current?.contains(e.target as Node)) setRunMenu(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || document.querySelector(".scrim")) return;
      setRunMenu(false);
    };
    document.addEventListener("mousedown", close);
    window.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", close);
      window.removeEventListener("keydown", onKey);
    };
  }, [runMenu]);
  // Honour a request to move the user's place. "edit" is consumed by the cell's Editor (it waits
  // for the editor to load); "command" puts the focus on the cell itself, rendering markdown.
  const reqN = p.request?.n;
  useEffect(() => {
    const r = p.request;
    if (!r) return;
    if (r.mode === "command" || collapsed) {
      if (isMd && !composing.current) setEditing(false);
      section.current?.focus();
      p.onRequestDone(r.n);
    } else if (isMd) {
      if (!readOnly) { setHostReady(false); setEditing(true); }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [reqN]);

  return (
    <section
      ref={section}
      /* The cell itself is focusable (not tabbable except the current one): focused = COMMAND mode,
         where single keys act on the cell. A click on the cell's chrome lands here too. */
      tabIndex={focused || index === 0 ? 0 : -1}
      className={`cell-block${focused ? " is-focused" : ""}${selected ? " is-selected" : ""}${isMd ? " is-md" : ""}${runMenu ? " is-menu" : ""}`}
      onClick={(e) => {
        if ((e.target as HTMLElement).closest("button, a, input, textarea, .cm-editor")) return;
        p.onSelectClick(e);
      }}
      aria-label={`Cell ${index + 1}${isMd ? ", markdown" : ", code"}`}
      aria-keyshortcuts="Enter Shift+Enter Control+Enter Alt+Enter Escape"
      data-cell={index + 1}
      data-mode={isMd && !wantsEdit ? "read" : "edit"}
      onCompositionStart={() => { composing.current = true; dispatchView({ type: "compositionStart" }); }}
      onCompositionEnd={() => { composing.current = false; dispatchView({ type: "compositionEnd" }); }}
      /* Focus anywhere inside the cell (its editor, its buttons) is "this cell is current". React's
         onFocus/onBlur bubble like focusin/focusout, so one pair on the section covers all of it; the
         blur only counts when focus leaves the cell, not when it moves between two controls inside. */
      onFocus={(e) => p.onFocus(e.target === e.currentTarget ? "command" : "edit")}
      onBlur={(e) => {
        if (e.currentTarget.contains(e.relatedTarget as Node | null)) return;
        p.onBlur();
        // Leaving a markdown cell renders it (Databricks). Not when the whole window lost focus: the
        // user switching app and coming back must find the cell as they left it.
        if (isMd && editing && document.hasFocus() && !composing.current) setEditing(false);
      }}
    >
      <div className="cell-gutter" onMouseDown={(e) => {
        if ((e.target as HTMLElement).closest("button")) return;
        e.preventDefault();
        section.current?.focus();
      }}>
        <span className="cell-no" aria-hidden>{index + 1}</span>
        {/* No run button: there is no executor here, and a control that cannot act must not be shown
            (spec 006 00 P4, NB-2, 11 D3). Asking ABOUT the cell is offered instead, below. */}
      </div>

      <div className="cell-main">
        <div className={isMd && wantsEdit ? "markdown-authoring-chrome" : undefined}>
        <header className="cell-bar"
          /* KB-4: one Tab stop per cell. Its controls are reachable with ←/→ from the cell, instead of
             six Tab presses before the text. Buttons keep their names and clicks; only their Tab entry
             changes, via `tabIndex={-1}` below, so a pointer user sees no difference. */
          onKeyDown={(e) => {
            if (e.key !== "ArrowRight" && e.key !== "ArrowLeft" && e.key !== "Home" && e.key !== "End") return;
            const bar = e.currentTarget;
            if (!bar.contains(e.target as Node)) return;
            const stops = [...bar.querySelectorAll<HTMLElement>("button:not([disabled])")]
              .filter((b) => b.offsetParent !== null);
            if (stops.length === 0) return;
            const at = stops.indexOf(e.target as HTMLElement);
            if (at < 0) return;
            e.preventDefault();
            const to = e.key === "Home" ? 0 : e.key === "End" ? stops.length - 1
              : at + (e.key === "ArrowRight" ? 1 : -1);
            stops[Math.max(0, Math.min(stops.length - 1, to))]?.focus();
          }}>
          <button className="cell-collapse" tabIndex={-1} aria-expanded={!collapsed}
            aria-label={collapsed ? `Expand cell ${index + 1}` : `Collapse cell ${index + 1}`}
            onClick={p.onToggleCollapse}>
            {collapsed ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
          </button>
          <span className={`cell-kind is-${cell.kind}`}>{isMd ? "md" : ({ python: "py", sql: "sql", scala: "scala", r: "r" }[(cell.language || "").toLowerCase()] || (cell.language || "code").slice(0, 4))}</span>
          {isMd && <span className="markdown-mode-label">{wantsEdit ? "Editing Markdown" : readOnly ? "Read only" : "Preview"}</span>}
          {isMd && !readOnly && <button type="button" className="markdown-mode-toggle btn sm" aria-label={wantsEdit ? `Show preview of cell ${index + 1}` : `Edit Markdown cell ${index + 1}`}
            onMouseDown={e => e.preventDefault()} onClick={() => wantsEdit ? preview() : p.onEdit()}>{wantsEdit ? "Show preview" : "Edit"}</button>}

          <span className="cell-actions">
            {!readOnly && (
              <button className="cell-act" tabIndex={-1} onClick={() => p.onConvert(isMd ? "code" : "markdown")}
                title={isMd ? "Convert to code" : "Convert to markdown"}>
                {isMd ? "→ code" : "→ md"}
              </button>
            )}
            <button className="cell-act cell-ask" tabIndex={-1} onClick={p.onAsk} aria-pressed={p.prompting}
              title={`Ask the agent about cell ${index + 1} (${display("mod+shift+i")})`}
              aria-label={`Ask the agent about cell ${index + 1}`}>
              <Sparkle size={11} /> Ask
            </button>
            {p.onCopyLink && (
              <button className="cell-act" tabIndex={-1} onClick={p.onCopyLink}
                title={`Copy a link to cell ${index + 1}`} aria-label={`Copy a link to cell ${index + 1}`}>
                <LinkIcon size={12} />
              </button>
            )}
            {!readOnly && !isMd && (
              <span className="cell-run-group">
                <button className="cell-act cell-run-act" tabIndex={-1}
                  aria-label={`Run cell ${index + 1}`} title={affordance.title}
                  disabled={!affordance.enabled}
                  onClick={p.onRun}>
                  <Play size={10} /> Run
                </button>
                <button className="cell-act cell-run-more" tabIndex={-1} aria-expanded={runMenu}
                  aria-label={`More ways to run cell ${index + 1}`}
                  onClick={() => setRunMenu((v) => !v)}>▾</button>
                {runMenu && (
                  <span className="cell-run-menu" role="menu">
                    <button type="button" role="menuitem" disabled={!p.aboveEnabled}
                      title={p.aboveEnabled ? "Run every cell above this one, and stop at the first failure" : "Nothing above this cell can run"}
                      onClick={() => { setRunMenu(false); p.onRunSpan("above"); }}>Run all above</button>
                    <button type="button" role="menuitem" disabled={!p.belowEnabled}
                      title={p.belowEnabled ? "Run this cell and every cell below it, and stop at the first failure" : "Nothing here or below can run"}
                      onClick={() => { setRunMenu(false); p.onRunSpan("below"); }}>Run all below</button>
                  </span>
                )}
              </span>
            )}
            {!readOnly && (
              <>
                <button className="cell-act" tabIndex={-1} aria-label={`Add a cell after ${index + 1}`}
                  onClick={() => p.onInsertAfter("code")} title="Add a code cell below"><Plus size={12} /></button>
                <button className="cell-act cell-del" tabIndex={-1} aria-label={`Delete cell ${index + 1}`}
                  onClick={p.onDelete} title="Delete this cell"><Close size={12} /></button>
              </>
            )}
          </span>
        </header>
        {isMd && wantsEdit && !collapsed && <MarkdownToolbar host={editorHost} disabled={readOnly || !hostReady} documentPath={p.documentPath} />}
        </div>

        {p.prompting && (
          <CellPrompt mode="edit" label={`cell ${index + 1}`} onClose={p.onClosePrompt} onSend={p.onPromptSend}
            onDiscuss={p.onDiscuss} />
        )}

        {!collapsed && (
          <div className="cell-body">
            {isMd && !wantsEdit ? (
              <div className="cell-rendered" title={readOnly ? undefined : "Double-click to edit"}
                onDoubleClick={e => { if (!readOnly && !(e.target as HTMLElement).closest("a,button,input") && !window.getSelection()?.toString()) p.onEdit(); }}>
                <Markdown text={cell.source} model={p.markdownModel} surface="notebook" namespace={`${p.documentPath || "notebook"}:${cell.id}`} documentPath={p.documentPath} />
              </div>
            ) : (
              <Editor
                retainedState={isMd ? retainedState : undefined}
                onReady={host => { editorHost.current = host; setHostReady(true); }}
                value={cell.source}
                language={isMd ? "markdown" : cell.language}
                readOnly={readOnly}
                theme={theme}
                onChange={p.onSource}
                /* ⌘S inside a cell must save the DOCUMENT. CodeMirror's keymap consumes the key
                   before it can bubble, so if this handler does anything else — exiting markdown
                   edit mode, say — the save silently never happens. That was the real reason the
                   e2e scene saw no request at all while a button click worked. */
                onSave={() => p.onSave()}
                onChord={p.onChord}
                onCaret={p.onCaret}
                focusRequest={p.request?.mode === "edit" ? { n: p.request.n, at: p.request.at } : null}
                onFocusDone={p.onRequestDone}
                autoFocus={false}
                ariaLabel={`Cell ${index + 1} source`}
              />
            )}
          </div>
        )}
        {p.run && !collapsed && (
          <div className="cell-output-wrap">
            <CellOutput run={p.run} onClear={p.onClearRun} onView={p.onRunView} folded={p.outputHidden} onToggleFold={p.onToggleOutput}
              onFix={p.onFix && p.run.error ? () => p.onFix?.(p.run?.error ?? "") : undefined} />
          </div>
        )}
        {isMd && (wantsEdit || collapsed) && <div className="markdown-print-only"><Markdown text={cell.source} model={p.markdownModel} surface="notebook" namespace={`print:${p.documentPath}:${cell.id}`} documentPath={p.documentPath} /></div>}
      </div>
    </section>
  );
}
