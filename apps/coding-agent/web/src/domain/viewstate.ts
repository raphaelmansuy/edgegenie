/** Where the user was in a document: which cell, where in it, how far down. Pure + a tiny store.
 *
 * Kept per path for the life of the tab (sessionStorage, so a reload keeps it too), so that closing a
 * tab, switching documents, an approval dialog or an outside change never costs the user their place.
 * Geometry only: never content.
 */
export interface ViewState {
  /** 1-based cell the caret or selection was in; 0 = none. */
  cell: number;
  /** Character offset inside that cell. */
  caret: number;
  /** "edit": the caret was in the text. "command": the cell was selected. */
  mode: "edit" | "command";
  scroll: number;
}

const KEY = "coding-agent:view:v1";
const MAX = 60;
const memory = new Map<string, ViewState>();
let loaded = false;

function load() {
  if (loaded) return;
  loaded = true;
  try {
    const raw = typeof sessionStorage !== "undefined" ? sessionStorage.getItem(KEY) : null;
    if (!raw) return;
    for (const [path, v] of Object.entries(JSON.parse(raw) as Record<string, ViewState>)) {
      if (valid(v)) memory.set(path, v);
    }
  } catch { /* a corrupt entry is not worth a crash */ }
}

function valid(v: unknown): v is ViewState {
  const s = v as ViewState;
  return !!s && Number.isFinite(s.cell) && Number.isFinite(s.caret) && Number.isFinite(s.scroll) && (s.mode === "edit" || s.mode === "command");
}

export function recall(path: string): ViewState | null {
  load();
  return memory.get(path) ?? null;
}

export function remember(path: string, patch: Partial<ViewState>): void {
  load();
  const cur = memory.get(path) ?? { cell: 0, caret: 0, mode: "command" as const, scroll: 0 };
  memory.delete(path);                       // most recent last, so the oldest is evicted first
  memory.set(path, { ...cur, ...patch });
  while (memory.size > MAX) memory.delete(memory.keys().next().value as string);
  try {
    if (typeof sessionStorage !== "undefined") sessionStorage.setItem(KEY, JSON.stringify(Object.fromEntries(memory)));
  } catch { /* storage full or disabled: memory still works */ }
}

export function forget(path: string): void {
  load();
  memory.delete(path);
}

/** A state that no longer fits the notebook (it shrank) is pulled back inside it. */
export function clampTo(state: ViewState, cellCount: number, sourceLength: (cell: number) => number): ViewState {
  if (cellCount === 0 || state.cell < 1) return { ...state, cell: 0, caret: 0 };
  const cell = Math.min(state.cell, cellCount);
  return { ...state, cell, caret: Math.max(0, Math.min(state.caret, sourceLength(cell))) };
}
