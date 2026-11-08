/** The editor, mounted once and never controlled by React.
 *
 * This component exists to hold exactly one piece of React state (`ready`) and to own the lifetime
 * of an `EditorHost`. It deliberately does **not** keep the document in state: doing so would
 * re-render this component — and through it the work surface — on every keystroke, which is the
 * single performance mistake ED-2 exists to prevent.
 *
 * Data flow:
 *   parent -> setValue (on load, on recovery, on diff apply)
 *   editor -> onChange -> debounced -> draft + dirty flag
 *   ⌘S     -> onSave -> the app's save path
 */
import { useEffect, useRef, useState } from "react";
import { loadEditorHost, type EditorChord, type EditorHost } from "../editor/host";

interface Props {
  /** The document text to show. A change here *replaces* the buffer (load, recover, apply diff). */
  value: string;
  language: string;
  readOnly?: boolean;
  theme: "light" | "dark";
  /** Called after the document changes, debounced by the caller. */
  onChange: (value: string) => void;
  onSave: () => void;
  /** Focus the editor when it mounts (opening a document to type immediately). */
  autoFocus?: boolean;
  ariaLabel: string;
  /** Cell chords (Shift/⌘/Alt+Enter, Esc). Return true when handled. */
  onChord?: (chord: EditorChord) => boolean;
  /** The caret moved (character offset): lets the app remember the user's place. */
  onCaret?: (pos: number) => void;
  /** A request to put the caret in this editor. `n` makes each request distinct, so asking twice for
   *  the same place works, and a stale request is never replayed on a remount. It waits for the
   *  editor to finish loading. `onFocusDone` fires once it has been honoured. */
  focusRequest?: { n: number; at?: number } | null;
  onFocusDone?: (n: number) => void;
}

export function Editor({
  value, language, readOnly = false, theme, onChange, onSave, autoFocus = false, ariaLabel,
  onChord, onCaret, focusRequest, onFocusDone,
}: Props) {
  const host = useRef<HTMLDivElement>(null);
  const editor = useRef<EditorHost | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  /** The last value we handed to the editor. Used to avoid echoing our own change back into it. */
  const applied = useRef<string>("");
  /** Captured once. `autoFocus` as a live prop would focus every cell whose flag flips, so typing
   *  in one cell could pull focus into another. */
  const focusOnMount = useRef(autoFocus);
  const handlers = useRef({ onChange, onSave, onChord, onCaret, onFocusDone });
  handlers.current = { onChange, onSave, onChord, onCaret, onFocusDone };
  const honoured = useRef(0);

  // Mount once. Language/theme/readOnly changes are reconfigurations, not remounts, so the document
  // and the cursor survive them — a remount on every prop change would lose the caret mid-typing.
  useEffect(() => {
    let live = true;
    let local: EditorHost | null = null;
    void (async () => {
      try {
        const create = await loadEditorHost();
        if (!live || !host.current) return;
        local = create({
          readOnly,
          theme,
          onSave: () => handlers.current.onSave(),
          onChord: (chord) => handlers.current.onChord?.(chord) ?? false,
        });
        local.mount(host.current, value, language);
        local.onChange((next) => handlers.current.onChange(next));
        local.onCaret((pos) => handlers.current.onCaret?.(pos));
        applied.current = value;
        editor.current = local;
        setStatus("ready");
        if (focusOnMount.current) local.focus();
      } catch {
        if (live) setStatus("error");
      }
    })();
    return () => {
      live = false;
      local?.destroy();
      editor.current = null;
    };
    // Intentionally only on mount: everything else is a reconfigure below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // A new value from above (a load, a recovery, a diff apply). Not a keystroke: those never come
  // through here, because `value` does not track typing.
  useEffect(() => {
    const ed = editor.current;
    if (!ed || status !== "ready") return;
    if (value === applied.current) return;
    ed.setValue(value);
    applied.current = value;
    /* No focus() here on purpose. Refocusing on every value change steals the caret from whatever
       the user is actually typing in — with several cells mounted, that is how typed text ended up
       interleaved into the wrong cell. Focus belongs to the user (or to an explicit open), never to
       a data update. */
  }, [value, status]);

  // An explicit request to put the caret here. Waits for `ready`, so a markdown cell that has just
  // switched from rendered to editing still receives it once its editor has loaded.
  const reqN = focusRequest?.n ?? 0;
  const reqAt = focusRequest?.at;
  useEffect(() => {
    const ed = editor.current;
    if (!ed || status !== "ready" || !reqN || reqN === honoured.current) return;
    honoured.current = reqN;
    ed.focus(reqAt);
    handlers.current.onFocusDone?.(reqN);
  }, [reqN, reqAt, status]);

  useEffect(() => {
    editor.current?.reconfigure(language);
  }, [language]);

  return (
    <div className="editor-host" data-status={status}>
      {/* The pane is reserved at its final height *before* the editor loads, so mounting it adds
          no layout shift. That is what keeps audit:cls at 0 with a 250 KB chunk arriving late. */}
      <div className="editor-mount" ref={host} role="textbox" aria-multiline="true" aria-label={ariaLabel}
        aria-readonly={readOnly || undefined} />
      {status === "loading" && <p className="editor-note" role="status">loading the editor…</p>}
      {status === "error" && (
        <p className="editor-note" role="alert">
          The editor could not load. The text below is still readable and you can copy it.
        </p>
      )}
      {status === "error" && <pre className="editor-fallback">{value}</pre>}
    </div>
  );
}
