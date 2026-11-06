/** Command palette: ⌘K to do anything without the mouse. Accessible as a modal dialog.
 *
 * This is the single biggest difference between an app that feels fast and one that feels like a web
 * form: every object, panel, tab and action is one query away, ranked by fuzzy match, arrow keys move,
 * Enter runs, Escape leaves. Modelled on the palettes people judge apps by (Raycast, Linear, Cursor).
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import { highlight, rank, type Candidate } from "../domain/fuzzy";

/** Live results from the workspace and the catalog, appended to the local ones.
 *
 * A palette that only knows what is already open is a menu. Typing four letters here should find the
 * notebook, the table, the session or the command — the same three kinds of thing Genie Code's `@`
 * offers, and the reason a palette is faster than a mouse.
 */
function useRemote(query: string): Candidate[] {
  const [found, setFound] = useState<Candidate[]>([]);
  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) { setFound([]); return; }
    let live = true;
    // Each source fills in as it answers. Waiting for both would make the catalogue — which is
    // fast — appear only after the workspace walk, which is slow.
    const take = (add: (rows: Candidate[]) => void) => (rows: Candidate[]) => { if (live) add(rows); };
    const id = window.setTimeout(() => {
      api.findTables(q)
        .then((r) => r.results.slice(0, 6).map((t) => ({
          id: `open:table:${t.ref}`, title: t.name, hint: t.ref, group: "Tables",
          keywords: t.ref, weight: 4, run: () => onOpenTable(t.ref),
        })))
        .then(take((rows) => setFound((cur) => [...rows, ...cur.filter((c) => !c.id.startsWith("open:table:"))])))
        .catch(() => {});
      api.search(q)
        .then((r) => r.results.filter((h) => h.kind !== "directory").slice(0, 6).map((f) => ({
          id: `open:${f.kind}:${f.path}`, title: f.name, hint: f.path.split("/").slice(0, -1).join("/"),
          group: f.kind === "notebook" ? "Notebooks" : "Files", keywords: f.path, weight: 4,
          run: () => onOpenFile(f.kind, f.path),
        })))
        .then(take((rows) => setFound((cur) => [...cur.filter((c) => c.id.startsWith("open:table:")), ...rows])))
        .catch(() => {});
    }, 120);
    return () => { live = false; window.clearTimeout(id); };
  }, [query]);
  return found;
}

/** Wired by the app: the palette opens objects, it does not render them. */
export const PaletteActions = { onOpenTable: (_ref: string) => {}, onOpenFile: (_kind: string, _path: string) => {} };
const onOpenTable = (ref: string) => PaletteActions.onOpenTable(ref);
const onOpenFile = (kind: string, path: string) => PaletteActions.onOpenFile(kind, path);

export function Palette({ items, onClose }: { items: Candidate[]; onClose: () => void }) {
  const [query, setQuery] = useState("");
  const [pick, setPick] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLDivElement>(null);

  useEffect(() => {
    input.current?.focus();
  }, []);

  const remote = useRemote(query);
  const all = useMemo(() => {
    // Local actions first: a command the user typed on purpose should never be pushed down by a file.
    const seen = new Set(items.map((i) => i.id));
    return [...items, ...remote.filter((r) => !seen.has(r.id))];
  }, [items, remote]);
  const results = useMemo(() => rank(all, query, 16), [all, query]);

  useEffect(() => {
    setPick(0);
  }, [query]);

  useEffect(() => {
    const el = list.current?.querySelector<HTMLElement>('[aria-selected="true"]');
    el?.scrollIntoView({ block: "nearest" });
  }, [pick]);

  const run = (c: Candidate) => {
    onClose();
    // After the dialog unmounts, so a command that focuses something else wins the focus fight.
    requestAnimationFrame(() => c.run());
  };

  const groups = useMemo(() => {
    const out: { group: string; rows: { c: Candidate; index: number }[] }[] = [];
    results.forEach((r, index) => {
      const last = out[out.length - 1];
      if (last?.group === r.candidate.group) last.rows.push({ c: r.candidate, index });
      else out.push({ group: r.candidate.group, rows: [{ c: r.candidate, index }] });
    });
    return out;
  }, [results]);

  return (
    <div className="scrim palette-scrim" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="palette" role="dialog" aria-modal="true" aria-label="Command palette">
        <input
          ref={input}
          className="palette-input"
          value={query}
          placeholder="Search files, tables, sessions and commands…"
          aria-label="Command palette"
          aria-controls="palette-list"
          aria-activedescendant={results[pick] ? `palette-${results[pick].candidate.id}` : undefined}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") { e.preventDefault(); setPick((p) => Math.min(p + 1, results.length - 1)); }
            else if (e.key === "ArrowUp") { e.preventDefault(); setPick((p) => Math.max(p - 1, 0)); }
            else if (e.key === "Enter" && results[pick]) { e.preventDefault(); run(results[pick].candidate); }
            else if (e.key === "Escape") { e.preventDefault(); onClose(); }
          }}
        />
        <div className="palette-list" id="palette-list" role="listbox" aria-label="Results" ref={list}>
          {results.length === 0 && <p className="palette-empty">Nothing matches “{query}”.</p>}
          {groups.map((g) => (
            <div key={g.group} className="palette-group">
              <div className="palette-group-name" aria-hidden>{g.group}</div>
              {g.rows.map(({ c, index }) => (
                <button
                  key={c.id}
                  id={`palette-${c.id}`}
                  role="option"
                  aria-selected={index === pick}
                  className={`palette-row${index === pick ? " is-active" : ""}`}
                  onMouseMove={() => setPick(index)}
                  onMouseDown={(e) => { e.preventDefault(); run(c); }}
                >
                  <span className="palette-title">
                    {highlight(c.title, query).map((r, i) => (r.hit ? <mark key={i}>{r.text}</mark> : <span key={i}>{r.text}</span>))}
                  </span>
                  {c.hint && <span className="palette-hint">{c.hint}</span>}
                </button>
              ))}
            </div>
          ))}
        </div>
        <footer className="palette-foot">
          <span><kbd>↑</kbd><kbd>↓</kbd> move</span>
          <span><kbd>⏎</kbd> open</span>
          <span><kbd>Esc</kbd> close</span>
        </footer>
      </div>
    </div>
  );
}
