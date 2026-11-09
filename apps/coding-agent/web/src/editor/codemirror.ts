/** The CodeMirror 6 implementation of EditorHost, and the theme that makes it look like this app.
 *
 * Everything CodeMirror-specific lives here. The rest of the codebase imports only `./host`.
 *
 * The theme is built from the app's CSS custom properties rather than a bundled editor theme, for a
 * reason that shows up immediately in review: a hand-built dark theme drifts from the app's own
 * dark mode, and then the editor looks like a different product embedded in the page. Reading
 * `--blue-600`, `--surface`, `--line` at mount time means one source of truth and no second palette
 * to keep in step (spec 003 lens 5).
 */
import { EditorState, Compartment, type Extension } from "@codemirror/state";
import {
  EditorView, keymap, lineNumbers, highlightActiveLine, highlightActiveLineGutter,
  drawSelection, dropCursor, rectangularSelection, crosshairCursor, highlightSpecialChars,
} from "@codemirror/view";
import { defaultKeymap, history, historyKeymap, indentWithTab, toggleComment } from "@codemirror/commands";
import { searchKeymap, highlightSelectionMatches } from "@codemirror/search";
import { autocompletion, completionKeymap } from "@codemirror/autocomplete";
import { bracketMatching, foldGutter, foldKeymap, indentOnInput, syntaxHighlighting, HighlightStyle } from "@codemirror/language";
import { tags as t } from "@lezer/highlight";
import { python } from "@codemirror/lang-python";
import { sql } from "@codemirror/lang-sql";
import { json } from "@codemirror/lang-json";
import { javascript } from "@codemirror/lang-javascript";
import { markdown } from "@codemirror/lang-markdown";
import type { EditorHost, EditorHostFactory } from "./host";
import { minimalChange } from "./diff";

/** Language id -> parser. Unknown languages get no parser, which CodeMirror treats as plain text —
 *  the same "showing the source is always safe, guessing is not" rule as the notebook parser. */
function parserFor(language: string): Extension {
  switch ((language || "").toLowerCase()) {
    case "python": case "py": return python();
    case "sql": return sql();
    case "json": return json();
    case "javascript": case "js": case "typescript": case "ts": return javascript({ typescript: /ts$/.test(language) });
    case "markdown": case "md": return markdown();
    default: return [];
  }
}

/** Read a token from the document at mount time. Falls back to a sane default so an editor mounted
 *  before the stylesheet applies is still legible rather than black-on-black. */
function token(name: string, fallback: string): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

function highlight(theme: "light" | "dark"): Extension {
  const c = (n: string, d: string) => token(n, d);
  /* Every colour here is a FOREGROUND, so every token it reads must be a text-weight one. Three of
     these were reading a `-300` tint — `--purple-300` for keywords, `--orange-300` for numbers,
     `--teal-300` for type names — and a tint on the editor surface measured 1.79:1, which is a
     keyword you cannot read (WCAG 1.4.3 wants 4.5:1). The `-700` tokens exist for exactly this, and
     the CodeMirror fallbacks below were already the right weight, which is what made the bug visible
     only when the stylesheet's token won. */
  const style = HighlightStyle.define([
    { tag: t.comment, color: c("--ink-3", theme === "dark" ? "#9b968f" : "#6b6760"), fontStyle: "italic" },
    { tag: [t.keyword, t.operatorKeyword, t.modifier], color: c("--purple-700", "#7652c2") },
    { tag: [t.string, t.special(t.string)], color: c("--green-700", "#25754b") },
    { tag: [t.number, t.bool, t.null], color: c("--orange-700", "#c0612b") },
    { tag: [t.function(t.variableName), t.function(t.propertyName)], color: c("--blue-600", "#4b5bd6") },
    { tag: [t.typeName, t.className, t.namespace], color: c("--teal-700", "#1e8580") },
    { tag: t.definition(t.variableName), color: c("--ink", "#1c1b19") },
    { tag: [t.propertyName, t.attributeName], color: c("--ink-2", "#57544e") },
    { tag: [t.punctuation, t.bracket], color: c("--ink-3", "#6b6760") },
    { tag: t.heading, color: c("--ink", "#1c1b19"), fontWeight: "650" },
    { tag: t.strong, fontWeight: "650" },
    { tag: t.emphasis, fontStyle: "italic" },
    { tag: t.link, color: c("--blue-600", "#4b5bd6"), textDecoration: "underline" },
    { tag: t.invalid, color: c("--pink-700", "#a33a5c") },
  ]);
  return [syntaxHighlighting(style), EditorView.theme(themeVars(theme))];
}

/** Chrome colours, from the same tokens the rest of the shell uses. */
function themeVars(theme: "light" | "dark"): Record<string, Record<string, string>> {
  const c = (n: string, d: string) => token(n, d);
  const surface = c("--surface", theme === "dark" ? "#1c1c1b" : "#ffffff");
  const ink = c("--ink", theme === "dark" ? "#eceae6" : "#1c1b19");
  const line = c("--line", theme === "dark" ? "#2d2c2a" : "#e9e7e2");
  const accent = c("--blue-600", theme === "dark" ? "#93a3f2" : "#4b5bd6");
  return {
    "&": {
      color: ink,
      backgroundColor: surface,
      fontSize: "12.5px",
      height: "100%",
    },
    "&.cm-focused": { outline: "none" },
    ".cm-scroller": {
      fontFamily: c("--mono", "ui-monospace, SFMono-Regular, Menlo, monospace"),
      lineHeight: "1.55",
      overflow: "auto",
    },
    ".cm-content": { padding: "8px 0", caretColor: accent },
    ".cm-line": { padding: "0 12px 0 4px" },
    ".cm-gutters": {
      backgroundColor: surface, color: c("--ink-3", "#6b6760"),
      border: "none", borderRight: `1px solid ${line}`,
    },
    ".cm-lineNumbers .cm-gutterElement": { padding: "0 8px 0 12px", minWidth: "32px" },
    ".cm-activeLine": { backgroundColor: theme === "dark" ? "rgba(255,255,255,0.035)" : "rgba(0,0,0,0.026)" },
    ".cm-activeLineGutter": { backgroundColor: "transparent", color: ink },
    "&.cm-focused .cm-selectionBackground, .cm-selectionBackground, ::selection": {
      backgroundColor: theme === "dark" ? "rgba(147,163,242,0.28)" : "rgba(75,91,214,0.16)",
    },
    ".cm-cursor, .cm-dropCursor": { borderLeftColor: accent, borderLeftWidth: "2px" },
    "&.cm-focused .cm-matchingBracket": {
      backgroundColor: theme === "dark" ? "rgba(147,163,242,0.24)" : "rgba(75,91,214,0.12)",
      outline: `1px solid ${accent}`, borderRadius: "2px",
    },
    ".cm-foldPlaceholder": { backgroundColor: c("--surface-3", "#efede9"), border: "none", color: c("--ink-3", "#6b6760") },
    ".cm-panels": { backgroundColor: c("--surface-2", "#f6f5f2"), color: ink, borderTop: `1px solid ${line}` },
    ".cm-searchMatch": { backgroundColor: theme === "dark" ? "rgba(230,205,138,0.22)" : "rgba(242,217,141,0.5)" },
    ".cm-searchMatch.cm-searchMatch-selected": { backgroundColor: theme === "dark" ? "rgba(230,205,138,0.4)" : "rgba(242,217,141,0.9)" },
    ".cm-tooltip": {
      backgroundColor: c("--surface", "#ffffff"), border: `1px solid ${line}`,
      borderRadius: "6px", boxShadow: c("--shadow-lg", "0 12px 32px rgba(0,0,0,0.16)"),
    },
    ".cm-tooltip-autocomplete > ul > li[aria-selected]": {
      backgroundColor: c("--surface-3", "#efede9"), color: ink,
    },
  };
}

export const createEditorHost: EditorHostFactory = ({ readOnly = false, theme, onSave, onChord }) => {
  let view: EditorView | null = null;
  const languageConf = new Compartment();
  const themeConf = new Compartment();
  const readOnlyConf = new Compartment();
  const changeCbs: ((v: string, docChanged: boolean) => void)[] = [];
  const cellCbs: ((id: string | null) => void)[] = [];
  const caretCbs: ((pos: number) => void)[] = [];
  /** True while we are replacing the document ourselves. A programmatic write is not an edit: if it
   *  were reported as one, opening a file would immediately show "unsaved". */
  let silent = false;

  const extensions = (): Extension[] => [
    lineNumbers(),
    highlightActiveLineGutter(),
    highlightSpecialChars(),
    history(),
    drawSelection(),
    dropCursor(),
    EditorState.allowMultipleSelections.of(true),
    indentOnInput(),
    bracketMatching(),
    autocompletion(),
    rectangularSelection(),
    crosshairCursor(),
    highlightActiveLine(),
    highlightSelectionMatches(),
    foldGutter({ openText: "▾", closedText: "▸" }),
    keymap.of([
      // ⌘S is the app's, not the browser's: the editor must never show "Save page?".
      { key: "Mod-s", preventDefault: true, run: () => { onSave?.(); return true; } },
      { key: "Mod-/", preventDefault: true, run: toggleComment },
      { key: "Shift-Enter", preventDefault: true, run: () => onChord?.("run-next") ?? false },
      { key: "Mod-Enter", preventDefault: true, run: () => onChord?.("run-stay") ?? false },
      { key: "Alt-Enter", preventDefault: true, run: () => onChord?.("run-insert") ?? false },
      { key: "Alt-Shift-Enter", preventDefault: true, run: () => onChord?.("run-all") ?? false },
      { key: "Alt-Shift-ArrowUp", preventDefault: true, run: () => onChord?.("run-above") ?? false },
      { key: "Alt-Shift-ArrowDown", preventDefault: true, run: () => onChord?.("run-below") ?? false },
      { key: "Mod-Alt--", preventDefault: true, run: () => onChord?.("split") ?? false },
      ...completionKeymap,
      // After completionKeymap on purpose: Esc closes an open completion list first.
      { key: "Escape", run: () => onChord?.("escape") ?? false },
      ...searchKeymap, ...historyKeymap, ...foldKeymap,
      ...defaultKeymap, indentWithTab,
    ]),
    readOnlyConf.of(EditorState.readOnly.of(readOnly)),
    languageConf.of(parserFor("python")),
    themeConf.of(highlight(theme)),
    EditorView.updateListener.of((u) => {
      if (u.docChanged && !silent) {
        const v = u.state.doc.toString();
        for (const cb of changeCbs) cb(v, true);
      }
      if ((u.selectionSet || u.docChanged) && !silent) {
        const pos = u.state.selection.main.head;
        for (const cb of caretCbs) cb(pos);
      }
    }),
    EditorView.domEventHandlers({
      focus: () => { for (const cb of cellCbs) cb(null); },
    }),
  ];

  return {
    mount(parent, initial, language) {
      this.destroy();
      parent.replaceChildren();
      view = new EditorView({
        state: EditorState.create({ doc: initial, extensions: extensions() }),
        parent,
      });
      view.dispatch({ effects: languageConf.reconfigure(parserFor(language)) });
    },
    getValue: () => view?.state.doc.toString() ?? "",
    setValue(next) {
      if (!view) return;
      silent = true;
      try {
        // Replace only what differs. A whole-document replace collapses the caret to the start and
        // scrolls the cell; a minimal change lets CodeMirror map the caret and selection through it,
        // so an outside edit elsewhere in the cell leaves the user exactly where they were.
        const change = minimalChange(view.state.doc.toString(), next);
        if (change) view.dispatch({ changes: change });
      } finally {
        silent = false;
      }
    },
    onChange(cb) { changeCbs.push(cb); },
    onCellFocus(cb) { cellCbs.push(cb); },
    reconfigure(language) {
      view?.dispatch({ effects: languageConf.reconfigure(parserFor(language)) });
    },
    focus(at) {
      if (!view) return;
      view.focus();
      if (typeof at === "number") {
        const pos = Math.max(0, Math.min(at, view.state.doc.length));
        view.dispatch({ selection: { anchor: pos }, scrollIntoView: true });
      }
    },
    getCaret: () => view?.state.selection.main.head ?? 0,
    onCaret(cb) { caretCbs.push(cb); },
    blur() { view?.contentDOM.blur(); },
    destroy() {
      view?.destroy();
      view = null;
      changeCbs.length = 0;
      cellCbs.length = 0;
      caretCbs.length = 0;
    },
  } satisfies EditorHost;
};
