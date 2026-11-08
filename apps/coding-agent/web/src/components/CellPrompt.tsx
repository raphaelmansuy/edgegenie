/** The inline prompt on a cell: type what you want where you are looking.
 *
 * Genie Code's cell says "Start typing or generate with AI (⌘ I)". This is that: a small bar that opens
 * under the cell header (edit) or in the gap between two cells (insert), takes one instruction, and
 * sends it to the assistant bound to that cell. The conversation itself still happens in the dock, so
 * there is one transcript, one stop button and one approval flow; this is only a faster way in.
 *
 * Keyboard: Enter sends, Shift+Enter breaks the line, Escape closes and gives focus back to the cell.
 */
import { useEffect, useRef, useState } from "react";
import { CELL_INTENTS } from "../domain/cellprompt";
import { Close, Send, Sparkle } from "./Icons";

export type PromptMode = "edit" | "insert";

export function CellPrompt({ mode, label, onSend, onClose, onDiscuss }: {
  mode: PromptMode;
  /** What this prompt is about, for the screen reader and the placeholder: "cell 3" or "after cell 3". */
  label: string;
  onSend: (instruction: string) => void;
  onClose: () => void;
  /** Open the conversation in the dock instead (the old "ask" behaviour), when there is one. */
  onDiscuss?: () => void;
}) {
  const [text, setText] = useState("");
  const box = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { box.current?.focus(); }, []);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, [text]);

  const go = (value: string) => { const v = value.trim(); if (v) onSend(v); };

  return (
    <div className={`cell-prompt is-${mode}`} role="group" aria-label={mode === "edit" ? `Ask the agent about ${label}` : `Generate a cell ${label}`}>
      <span className="cell-prompt-mark" aria-hidden><Sparkle size={14} /></span>
      <div className="cell-prompt-main">
        <textarea
          ref={box}
          rows={1}
          value={text}
          placeholder={mode === "edit" ? `What should the agent do with ${label}?` : `Describe the cell to add ${label}`}
          aria-label={mode === "edit" ? `Instruction for ${label}` : `Describe the new cell ${label}`}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); go(text); }
            if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); onClose(); }
          }}
        />
        {mode === "edit" && (
          <div className="cell-prompt-chips" role="group" aria-label="Quick actions">
            {CELL_INTENTS.map((i) => (
              <button key={i.id} type="button" className="cell-chip" onClick={() => go(i.instruction)}>{i.label}</button>
            ))}
            {onDiscuss && (
              <button type="button" className="cell-chip is-link" onClick={onDiscuss}>Discuss in the assistant</button>
            )}
          </div>
        )}
      </div>
      <button type="button" className="btn sm primary cell-prompt-send" disabled={!text.trim()} onClick={() => go(text)}
        aria-label="Send to the agent"><Send size={12} /> Send</button>
      <button type="button" className="icon-btn cell-prompt-close" aria-label="Close" title="Close (Esc)" onClick={onClose}><Close size={13} /></button>
    </div>
  );
}
