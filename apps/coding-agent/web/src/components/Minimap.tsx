/** The execution map: a bar per code cell, and a list that names each one.
 *
 * The bars are the thing you see while scrolling. The pin (or focus inside the list) opens the
 * named list in its own column, so crossing the rail with the pointer does not cover the cell.
 */
import { useState } from "react";
import { toneWord, type ExecutionMap } from "../domain/minimap";

export function Minimap({ map, onJump }: { map: ExecutionMap; onJump: (index: number) => void }) {
  const [open, setOpen] = useState(false);
  if (map.rows.length === 0) return null;
  return (
    <nav className={`nb-map${open ? " is-open" : ""}`} aria-label="Execution map">
      <div className="nb-map-pop" role="group" aria-label="Cells">
        <header className="nb-map-head">
          <strong>Cells</strong>
          <span>{map.rows.length}</span>
        </header>
        <ul>
          {map.rows.map((row) => (
            <li key={row.id}>
              <button type="button" className="nb-map-row" data-tone={row.tone} onClick={() => onJump(row.index)}>
                <span className="nb-map-dot" data-tone={row.tone} aria-hidden />
                <span className="nb-map-no">{row.index}</span>
                <span className="nb-map-label">{row.label}</span>
                <span className="nb-map-state">{toneWord(row.tone)}</span>
              </button>
            </li>
          ))}
        </ul>
        {(map.firstFailed !== null || map.lastSettled !== null) && (
          <footer className="nb-map-foot">
            {map.firstFailed !== null && (
              <button type="button" className="btn sm" onClick={() => onJump(map.firstFailed!)}>First failed</button>
            )}
            {map.lastSettled !== null && (
              <button type="button" className="btn sm ghost" onClick={() => onJump(map.lastSettled!)}>Last run</button>
            )}
          </footer>
        )}
      </div>
      <div className="nb-map-rail">
        <div className="nb-map-bars">
          {map.rows.map((row) => (
            <button key={row.id} type="button" className="nb-map-bar" data-tone={row.tone} tabIndex={-1}
              aria-label={`Cell ${row.index}, ${toneWord(row.tone)}, ${row.label}`}
              title={`Cell ${row.index} · ${row.label}`}
              onClick={() => onJump(row.index)} />
          ))}
        </div>
        <button type="button" className="nb-map-pin" aria-expanded={open}
          aria-label={open ? "Hide the execution list" : "Show the execution list"}
          onClick={() => setOpen((v) => !v)}>
          <span aria-hidden />
        </button>
      </div>
    </nav>
  );
}
