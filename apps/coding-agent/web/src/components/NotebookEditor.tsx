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
import { useCallback, useState } from "react";
import {
  insertCell, moveCell, newCell, removeCell, setCellKind, updateCellSource, type Cell,
} from "../domain/notebook";
import { ChevronDown, ChevronRight, Close, Plus, Send } from "./Icons";
import { Editor } from "../editor/Editor";
import { Markdown } from "./Markdown";

interface Props {
  cells: Cell[];
  language: string;
  theme: "light" | "dark";
  readOnly?: boolean;
  onChange: (cells: Cell[]) => void;
  /** Ask the agent about one cell: the reason owning the editor is worth it (spec 003 lens 7). */
  onAskCell?: (cell: Cell, index: number) => void;
  /** Run one cell through the agent's execution path (NB-6: no second executor). */
  onRunCell?: (cell: Cell, index: number) => void;
}

export function NotebookEditor({
  cells, language, theme, readOnly = false, onChange, onAskCell, onRunCell,
}: Props) {
  const [focused, setFocused] = useState<string | null>(null);
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const set = useCallback((next: Cell[]) => onChange(next), [onChange]);

  const addAt = (at: number, kind: "code" | "markdown") => {
    const cell = newCell(kind, language);
    const next = insertCell(cells, at, cell);
    set(next);
    setFocused(cell.id);
  };

  // Keyboard model for the cell stack (NB-2). Escaping the editor is what lets you move cells.
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      (e.target as HTMLElement).blur();
      setFocused(null);
    }
  };

  return (
    <div className="cells" onKeyDown={onKey}>
      {cells.map((cell, i) => (
        <CellBlock
          key={cell.id}
          cell={cell}
          index={i}
          total={cells.length}
          language={language}
          theme={theme}
          readOnly={readOnly}
          focused={focused === cell.id}
          collapsed={collapsed.has(cell.id)}
          onFocus={() => setFocused(cell.id)}
          onBlur={() => setFocused((f) => (f === cell.id ? null : f))}
          onToggleCollapse={() => {
            const next = new Set(collapsed);
            if (next.has(cell.id)) next.delete(cell.id);
            else next.add(cell.id);
            setCollapsed(next);
          }}
          onSource={(src) => set(updateCellSource(cells, cell.id, src))}
          onMove={(to) => { set(moveCell(cells, i, to)); setFocused(cell.id); }}
          onDelete={() => { set(removeCell(cells, cell.id)); setFocused(null); }}
          onConvert={(kind) => set(setCellKind(cells, cell.id, kind, language))}
          onInsertAfter={(kind) => addAt(i + 1, kind)}
          onAsk={() => onAskCell?.(cell, i)}
          onRun={() => onRunCell?.(cell, i)}
        />
      ))}

      <div className="cells-add">
        <button className="btn sm" onClick={() => addAt(cells.length, "code")}>
          <Plus size={13} /> code
        </button>
        <button className="btn sm" onClick={() => addAt(cells.length, "markdown")}>
          <Plus size={13} /> markdown
        </button>
      </div>
    </div>
  );
}

interface CellProps {
  cell: Cell;
  index: number;
  total: number;
  language: string;
  theme: "light" | "dark";
  readOnly: boolean;
  focused: boolean;
  collapsed: boolean;
  onFocus: () => void;
  onBlur: () => void;
  onToggleCollapse: () => void;
  onSource: (s: string) => void;
  onMove: (to: number) => void;
  onDelete: () => void;
  onConvert: (kind: "code" | "markdown") => void;
  onInsertAfter: (kind: "code" | "markdown") => void;
  onAsk: () => void;
  onRun: () => void;
}

function CellBlock(p: CellProps) {
  const { cell, index, theme, readOnly, focused, collapsed } = p;
  const isMd = cell.kind === "markdown";
  /** A markdown cell shows prose until you enter it. Entering is a click or Enter on the block. */
  const [editing, setEditing] = useState(isMd ? false : true);
  // A fresh cell (empty source) should be editable immediately; that is what you meant by adding it.
  const wantsEdit = !isMd || editing || !cell.source.trim();

  return (
    <section
      className={`cell-block${focused ? " is-focused" : ""}${isMd ? " is-md" : ""}`}
      aria-label={`Cell ${index + 1}${isMd ? ", markdown" : ", code"}`}
      onMouseDown={(e) => {
        // Clicking anywhere in a rendered markdown cell puts you in it.
        if (isMd && !editing && (e.target as HTMLElement).closest(".cell-body")) setEditing(true);
      }}
    >
      <div className="cell-gutter">
        <span className="cell-no" aria-hidden>{index + 1}</span>
        {!readOnly && (
          <button className="cell-run" aria-label={`Run cell ${index + 1}`} title="Run this cell (⌘↵)"
            onClick={p.onRun}>
            <Send size={12} />
          </button>
        )}
      </div>

      <div className="cell-main">
        <header className="cell-bar">
          <button className="cell-collapse" aria-expanded={!collapsed}
            aria-label={collapsed ? `Expand cell ${index + 1}` : `Collapse cell ${index + 1}`}
            onClick={p.onToggleCollapse}>
            {collapsed ? <ChevronRight size={12} /> : <ChevronDown size={12} />}
          </button>
          <span className={`cell-kind is-${cell.kind}`}>{isMd ? "md" : (cell.language || "code").slice(0, 4)}</span>

          <span className="cell-actions">
            {!readOnly && (
              <button className="cell-act" onClick={() => p.onConvert(isMd ? "code" : "markdown")}
                title={isMd ? "Convert to code" : "Convert to markdown"}>
                {isMd ? "→ code" : "→ md"}
              </button>
            )}
            {focused && p.onAsk && (
              <button className="cell-act" onClick={p.onAsk} title="Ask the agent about this cell">
                ask
              </button>
            )}
            {!readOnly && (
              <>
                <button className="cell-act" aria-label={`Add a cell after ${index + 1}`}
                  onClick={() => p.onInsertAfter("code")} title="Add a code cell below"><Plus size={12} /></button>
                <button className="cell-act cell-del" aria-label={`Delete cell ${index + 1}`}
                  onClick={p.onDelete} title="Delete this cell"><Close size={12} /></button>
              </>
            )}
          </span>
        </header>

        {!collapsed && (
          <div className="cell-body">
            {isMd && !wantsEdit ? (
              <div className="cell-rendered" role="button" tabIndex={0}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); setEditing(true); } }}
                onClick={() => setEditing(true)}
                aria-label={`Markdown cell ${index + 1}, press Enter to edit`}>
                <Markdown text={cell.source || "*Empty markdown cell — click to edit*"} />
              </div>
            ) : (
              <Editor
                value={cell.source}
                language={isMd ? "markdown" : cell.language}
                readOnly={readOnly}
                theme={theme}
                onChange={p.onSource}
                onSave={() => { setEditing(false); }}
                autoFocus={false}
                ariaLabel={`Cell ${index + 1} source`}
              />
            )}
          </div>
        )}
      </div>
    </section>
  );
}
