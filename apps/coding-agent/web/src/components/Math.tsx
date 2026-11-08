/** Render TeX as typeset math, with the failure modes that matter in a chat answer handled.
 *
 * Three rules, each learned from how this goes wrong in real agents:
 *
 *  1. **Never throw into the answer.** KaTeX throws on invalid TeX, and an LLM writes invalid TeX
 *     regularly (a half-streamed `\frac{`, a macro it invented). A thrown error would unmount the whole
 *     transcript. Invalid math renders as its own source in a marked span, so the user sees the
 *     attempted equation and can read it.
 *  2. **Streaming shows progress, not an error.** While the answer is arriving, `$x^` is a half-typed
 *     formula, not a mistake. In `streaming` mode a throw shows the raw source *quietly* (no error
 *     styling); once the turn is done it is marked as invalid.
 *  3. **KaTeX is loaded lazily and once.** It is ~280 KB, and most answers have no math. The first span
 *     pulls the chunk; the module is cached by the bundler, so the second span is free. Meanwhile the
 *     raw source is shown in place, at the right size, so nothing jumps when the typesetting arrives.
 */
import { memo, useEffect, useRef, useState } from "react";
import type { MathSpan } from "../domain/math";

type Katex = typeof import("katex")["default"];

let loading: Promise<Katex> | null = null;
/** One import for the whole app. The stylesheet is imported with the module, so a page with no math
 *  never downloads either (Vite splits it into the same lazy chunk). */
function loadKatex(): Promise<Katex> {
  loading ??= Promise.all([import("katex"), import("katex/dist/katex.min.css")])
    .then(([mod]) => mod.default)
    .catch((e) => {
      loading = null;                       // let a later attempt retry a transient failure
      throw e;
    });
  return loading;
}

export interface MathProps {
  span: MathSpan;
  /** The answer is still arriving: a parse failure is expected and must not look like an error. */
  streaming?: boolean;
}

function MathView({ span, streaming = false }: MathProps) {
  /** The node KaTeX owns. React must NEVER put children in it: KaTeX replaces its contents, and a
   *  React child in there makes the next commit throw `removeChild ... is not a child of this node`,
   *  which unmounted the whole transcript (measured: seven page errors, blank screen). So the
   *  fallback source lives in a SEPARATE sibling, and this node is empty from React's point of view. */
  const host = useRef<HTMLSpanElement>(null);
  const [state, setState] = useState<"idle" | "ready" | "failed">("idle");

  useEffect(() => {
    let live = true;
    void loadKatex()
      .then((katex) => {
        if (!live || !host.current) return;
        try {
          katex.render(span.tex, host.current, {
            displayMode: span.mode === "display",
            throwOnError: true,
            // `strict: false` accepts the Unicode (×, −, π) that LLMs emit; strict mode throws on them.
            strict: false,
            // No `\color`/size macros from the model: an answer must not restyle the app.
            trust: false,
            output: "html",
            // Accessibility: KaTeX writes an invisible MathML copy for screen readers, which is the
            // only way a formula is readable aloud. It costs a little DOM and is worth it.
            maxSize: 12,
            errorColor: "currentColor",
          });
          if (live) setState("ready");
        } catch {
          if (live) setState("failed");
        }
      })
      .catch(() => { if (live) setState("failed"); });
    return () => { live = false; };
  }, [span.tex, span.mode]);

  const cls = [
    "math",
    span.mode === "display" ? "math-display" : "math-inline",
    state === "failed" ? "math-invalid" : "",
    state === "failed" && streaming ? "math-pending" : "",
  ].filter(Boolean).join(" ");

  /* One node holds either the fallback source or the typeset output. React does not own the children
     once KaTeX has written into the element, so the source is written by React ONLY until the first
     successful render (then `children` is null and React leaves KaTeX's DOM alone). Writing the source
     first means the formula is readable immediately and no layout jump happens when it typesets. */
  return (
    <span className={cls} data-tex={span.tex} role={span.mode === "display" ? "math" : undefined}
      title={state === "failed" && !streaming ? "This formula could not be typeset" : undefined}>
      {/* KaTeX's own node: always present, never given React children. */}
      <span className="math-rendered" ref={host} />
      {/* The fallback, in its own node, so removing it never touches KaTeX's DOM. */}
      {state !== "ready" && <span className="math-source">{span.tex}</span>}
    </span>
  );
}

export const Math = memo(MathView);
