/** Shared tree row and keyboard model for the Files and Catalog trees (WAI-ARIA tree pattern). */
import type { KeyboardEvent, MouseEvent as ReactMouseEvent, ReactNode } from "react";
import { ChevronRight, Icon } from "./Icons";

export interface RowAction { label: string; glyph: string; run?: (e: ReactMouseEvent) => void; href?: string | null }

export function TreeRow({ depth, role = "treeitem", expanded, selected, loading, caret, icon, iconClass, dim, name, title,
  badge, actions, onActivate, onKeyDown, onContextMenu }: {
  depth: number; role?: string; expanded?: boolean; selected?: boolean; loading?: boolean; caret: boolean;
  icon: string; iconClass: string; dim?: boolean; name: string; title?: string; badge?: ReactNode; actions?: RowAction[];
  onActivate: () => void; onKeyDown?: (e: KeyboardEvent<HTMLDivElement>) => void;
  onContextMenu?: (e: ReactMouseEvent<HTMLDivElement>) => void;
}) {
  return (
    <div
      role={role}
      aria-expanded={expanded}
      aria-selected={selected}
      aria-level={depth + 1}
      tabIndex={0}
      className={`tree-row${selected ? " is-selected" : ""}${dim ? " is-dim" : ""}`}
      style={{ paddingLeft: 8 + depth * 14 }}
      onClick={onActivate}
      onContextMenu={(e) => { if (!onContextMenu) return; e.preventDefault(); e.stopPropagation(); onContextMenu(e); }}
      onKeyDown={(e) => {
        if (e.target !== e.currentTarget) return;           // a key pressed inside an action button is its own
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onActivate(); return; }
        onKeyDown?.(e);
      }}
    >
      <span className={`tree-caret${expanded ? " is-open" : ""}`} aria-hidden>
        {caret ? <ChevronRight size={12} /> : null}
      </span>
      <span className={`tree-icon ${iconClass}`} aria-hidden><Icon kind={icon} /></span>
      <span className="tree-name" title={title ?? name}>{name}</span>
      {badge}
      {loading && <span className="spin" role="status" aria-label="loading" />}
      {actions && (
        <span className="tree-actions">
          {actions.map((a) => a.href ? (
            <a key={a.label} className="tree-act" href={a.href} target="_blank" rel="noopener noreferrer"
              title={a.label} aria-label={a.label} onClick={(e) => e.stopPropagation()}>{a.glyph}</a>
          ) : a.run ? (
            <button key={a.label} className="tree-act" title={a.label} aria-label={a.label}
              onClick={(e) => { e.stopPropagation(); a.run?.(e); }}>{a.glyph}</button>
          ) : null)}
        </span>
      )}
    </div>
  );
}

/** Up/Down/Home/End move focus between the visible rows of one tree. Left/Right are per-row. */
export function treeKeys(e: KeyboardEvent<HTMLElement>): void {
  if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) return;
  const tree = (e.target as HTMLElement).closest('[role="tree"]');
  if (!tree) return;
  const rows = Array.from(tree.querySelectorAll<HTMLElement>('[role="treeitem"]'));
  const at = rows.indexOf(e.target as HTMLElement);
  if (at < 0) return;
  e.preventDefault();
  const next = e.key === "Home" ? 0 : e.key === "End" ? rows.length - 1 : at + (e.key === "ArrowDown" ? 1 : -1);
  rows[Math.max(0, Math.min(rows.length - 1, next))]?.focus();
}

/** ArrowLeft on a row that cannot collapse moves focus to its parent folder. */
export function focusParent(row: HTMLElement): void {
  const level = Number(row.getAttribute("aria-level") ?? 1);
  const tree = row.closest('[role="tree"]');
  if (!tree || level <= 1) return;
  const rows = Array.from(tree.querySelectorAll<HTMLElement>('[role="treeitem"]'));
  for (let i = rows.indexOf(row) - 1; i >= 0; i--) {
    if (Number(rows[i].getAttribute("aria-level")) === level - 1) { rows[i].focus(); return; }
  }
}

/** ArrowRight on an open folder moves focus to its first child. */
export function focusFirstChild(row: HTMLElement): void {
  const tree = row.closest('[role="tree"]');
  if (!tree) return;
  const rows = Array.from(tree.querySelectorAll<HTMLElement>('[role="treeitem"]'));
  rows[rows.indexOf(row) + 1]?.focus();
}
