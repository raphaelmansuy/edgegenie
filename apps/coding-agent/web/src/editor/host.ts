/** The editor seam: the only file outside `editor/` that knows CodeMirror exists.
 *
 * Spec 003 D6. The app depends on this five-method interface, not on CodeMirror types, which buys
 * three things:
 *
 *  - **Testability.** A `textarea`-backed host satisfies it, so component tests run without a real
 *    editor and without a DOM-composition dance.
 *  - **No controlled component.** `getValue` / `setValue` are explicit calls, not props. A component
 *    that passes `value=` and reads `onChange=` re-renders the app on every keystroke — the exact
 *    thing ED-2 forbids. Here, keystrokes stay inside CodeMirror and only a debounced callback
 *    leaves.
 *  - **Swappability.** Monaco or a future engine means one new file, not a rewrite.
 *
 * The interface is deliberately small. Every extra method is a reason for a component to know more
 * about the editor than it should.
 */

export interface EditorHost {
  /** Attach to a container. Idempotent: calling twice replaces, never stacks. */
  mount(parent: HTMLElement, initial: string, language: string): void;
  /** The current text. The only way to read it; there is no `value` property to poll. */
  getValue(): string;
  /** Replace the whole document. Used for a recovery, a diff apply, or a cell rewrite. */
  setValue(next: string): void;
  /** Called after the document changes. `docChanged` is false for a selection-only change. */
  onChange(cb: (value: string, docChanged: boolean) => void): void;
  /** Called when the caret moves into a different cell (notebook mode only; null elsewhere). */
  onCellFocus(cb: (cellId: string | null) => void): void;
  /** Re-render with a different language or theme without losing the document or the cursor. */
  reconfigure(language: string): void;
  /** Focus the editor, optionally at a position (character offset). */
  focus(at?: number): void;
  /** Release listeners and DOM. Safe to call twice. */
  destroy(): void;
}

export type EditorHostFactory = (opts: {
  readOnly?: boolean;
  theme: "light" | "dark";
  /** Called for ⌘S so the app owns persistence, not the editor. */
  onSave?: () => void;
}) => EditorHost;

/** Load the real editor lazily.
 *
 * CodeMirror is ~250 KB gzipped with our languages, and most visits never open a document. The
 * dynamic import keeps it out of the initial bundle *and* out of `index.html`, so opening the app
 * costs the same as before this feature existed. It also means the editor's mount is the first
 * thing that can shift layout, which is why the pane reserves its height first (UX-3).
 */
export async function loadEditorHost(): Promise<EditorHostFactory> {
  const mod = await import("./codemirror");
  return mod.createEditorHost;
}
