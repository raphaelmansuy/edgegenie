/** One copy control for the whole app: a code block, an answer, a path. It says what happened. */
import { useEffect, useRef, useState } from "react";
import { copyText } from "../domain/clipboard";
import { Check } from "./Icons";

export function CopyButton({ text, label = "Copy", className = "copy-btn", title }: {
  text: string | (() => string); label?: string; className?: string; title?: string;
}) {
  const [state, setState] = useState<"idle" | "done" | "failed">("idle");
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  const click = async () => {
    const ok = await copyText(typeof text === "function" ? text() : text);
    setState(ok ? "done" : "failed");
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setState("idle"), 1600);
  };
  return (
    <button type="button" className={className} onClick={click} title={title ?? label}
      aria-label={state === "done" ? "Copied" : state === "failed" ? "Copy failed" : label}>
      {state === "done" ? <><Check size={12} /> Copied</> : state === "failed" ? "Copy failed" : label}
      <span className="sr-only" role="status" aria-live="polite">{state === "done" ? "Copied to the clipboard" : ""}</span>
    </button>
  );
}
