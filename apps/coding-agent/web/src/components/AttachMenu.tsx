/** The `+` menu: a real file picker, the existing context flow, and a placeholder that says what it will do.
 *
 * Three rows because the reported screen had three, and removing `Connectors` would be a regression in what
 * the product visibly offers. It is `aria-disabled` with a reason rather than a row that silently does
 * nothing — the difference between "not yet" and "broken".
 *
 * Keyboard: the trigger opens it, ArrowDown/Up move, Enter chooses, Escape closes and returns focus. That is
 * [AFC-19]: nothing here may need a mouse.
 */
import { useEffect, useId, useRef, useState } from "react";
import { FileIcon, Plug, Sparkle } from "./Icons";

export interface AttachMenuProps {
  onFiles: (files: FileList) => void;
  onContext: () => void;
  /** Present-but-not-available, with the reason shown. */
  connectorsReason?: string;
  disabled?: boolean;
}

export function AttachMenu({ onFiles, onContext, connectorsReason = "Connectors arrive in a later release", disabled }: AttachMenuProps) {
  const [open, setOpen] = useState(false);
  const [pick, setPick] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const id = useId();

  const rows = [
    { key: "files", label: "Attach files…", icon: <FileIcon size={14} />, hint: "", run: () => input.current?.click(), enabled: true },
    { key: "context", label: "Add context…", icon: <Sparkle size={14} />, hint: "", run: onContext, enabled: true },
    { key: "connectors", label: "Connectors", icon: <Plug size={14} />, hint: connectorsReason, run: () => {}, enabled: false },
  ];

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node;
      if (!menu.current?.contains(t) && !trigger.current?.contains(t)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const choose = (i: number) => {
    const row = rows[i];
    if (!row || !row.enabled) return;
    setOpen(false);
    row.run();
  };

  return (
    <span className="attach-wrap">
      <button
        ref={trigger}
        type="button"
        className="btn ghost icon-btn attach-trigger"
        aria-label="Attach a file"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? `${id}-menu` : undefined}
        title="Attach a file (⇧⌘A)"
        disabled={disabled}
        onClick={() => { setOpen((o) => !o); setPick(0); }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown" && !open) { e.preventDefault(); setOpen(true); setPick(0); }
        }}
      >
        <span aria-hidden className="attach-plus">+</span>
      </button>

      {/* Deliberately out of the accessibility tree AND out of the tab order: the `+` button above is the
          control a person operates, and a second 1×1 focusable input is both a duplicate stop and a
          pointer-target failure (measured: 7 findings, one per audited state). `display: none` would do the
          same job, but keeping the element in the DOM is what lets `click()` open the picker reliably. */}
      <input
        ref={input}
        type="file"
        multiple
        hidden
        aria-hidden="true"
        tabIndex={-1}
        onChange={(e) => {
          if (e.target.files && e.target.files.length) onFiles(e.target.files);
          e.target.value = "";       // so choosing the same file twice still fires
        }}
      />

      {open && (
        <div
          ref={menu}
          id={`${id}-menu`}
          className="attach-menu"
          role="menu"
          aria-label="Attach"
          onKeyDown={(e) => {
            if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); setOpen(false); trigger.current?.focus(); return; }
            if (e.key === "ArrowDown") { e.preventDefault(); setPick((p) => (p + 1) % rows.length); return; }
            if (e.key === "ArrowUp") { e.preventDefault(); setPick((p) => (p - 1 + rows.length) % rows.length); return; }
            if (e.key === "Enter" || e.key === " ") { e.preventDefault(); choose(pick); }
          }}
        >
          {rows.map((row, i) => (
            <button
              key={row.key}
              type="button"
              role="menuitem"
              className={`attach-row${i === pick ? " is-active" : ""}${row.enabled ? "" : " is-disabled"}`}
              aria-disabled={!row.enabled}
              ref={(el) => { if (el && i === pick) el.focus({ preventScroll: true }); }}
              onMouseEnter={() => setPick(i)}
              onClick={() => choose(i)}
            >
              <span className="attach-row-icon" aria-hidden>{row.icon}</span>
              <span className="attach-row-label">{row.label}</span>
              {row.hint && <span className="attach-row-hint">{row.hint}</span>}
            </button>
          ))}
        </div>
      )}
    </span>
  );
}
