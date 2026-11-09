/** A single keyboard and pointer contract for compact action menus. */
import { useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

export interface MenuAction {
  label: string; onSelect: () => void; disabled?: boolean; checked?: boolean; shortcut?: string;
}
export function ActionMenu({ label, children, actions, className = "btn ghost", title, description }: {
  label: string; children: ReactNode; actions: (MenuAction | null)[]; className?: string; title?: string; description?: string;
}) {
  const id = useId();
  const trigger = useRef<HTMLButtonElement>(null), menu = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState({ left: 8, top: 8 });
  const fromEnd = useRef(false);
  const buttons = () => Array.from(menu.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? []);
  const close = (restore = true) => { setOpen(false); if (restore) trigger.current?.focus({ preventScroll: true }); };
  useLayoutEffect(() => {
    if (!open || !trigger.current || !menu.current) return;
    const a = trigger.current.getBoundingClientRect(), box = menu.current.getBoundingClientRect();
    setPosition({ left: Math.max(8, Math.min(a.right - box.width, innerWidth - box.width - 8)),
      top: Math.max(8, Math.min(a.bottom + 6, innerHeight - box.height - 8)) });
    const items = buttons(); (fromEnd.current ? items.at(-1) : items[0])?.focus({ preventScroll: true });
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const outside = (e: PointerEvent) => {
      if (!menu.current?.contains(e.target as Node) && !trigger.current?.contains(e.target as Node)) close(false);
    };
    const focus = (e: FocusEvent) => {
      if (!menu.current?.contains(e.target as Node) && !trigger.current?.contains(e.target as Node)) close(false);
    };
    const resize = () => close();
    document.addEventListener("pointerdown", outside); document.addEventListener("focusin", focus);
    window.addEventListener("resize", resize);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("focusin", focus); window.removeEventListener("resize", resize); };
  }, [open]);
  return <>
    <button ref={trigger} className={className} aria-label={label} title={title ?? label}
      aria-haspopup="menu" aria-expanded={open} aria-controls={open ? id : undefined}
      onClick={() => { fromEnd.current = false; setOpen((v) => !v); }}
      onKeyDown={(e) => {
        if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); fromEnd.current = e.key === "ArrowUp"; setOpen(true); }
      }}>{children}</button>
    {open && createPortal(<div id={id} ref={menu} role="menu" aria-label={label} className="action-menu" style={position}
      onKeyDown={(e) => {
        const items = buttons(), at = items.indexOf(document.activeElement as HTMLButtonElement);
        if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); close(); }
        else if (["ArrowDown", "ArrowUp", "Home", "End"].includes(e.key)) {
          e.preventDefault();
          const index = e.key === "Home" ? 0 : e.key === "End" ? items.length - 1 : (at + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
          items[index]?.focus();
        } else if (e.key === "Tab") {
          e.preventDefault();
          const stops = Array.from(document.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input, textarea, [tabindex="0"]'))
            .filter((el) => el.tabIndex >= 0 && !!el.getBoundingClientRect().width && !menu.current?.contains(el));
          const index = stops.indexOf(trigger.current!); close(false); stops[index + (e.shiftKey ? -1 : 1)]?.focus();
        } else if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && e.key !== " ") {
          const next = [...items.slice(at + 1), ...items.slice(0, at + 1)].find((el) => el.textContent?.trim().toLowerCase().startsWith(e.key.toLowerCase()));
          if (next) { e.preventDefault(); next.focus(); }
        }
      }}>
      {description && <p className="action-menu-description">{description}</p>}
      {actions.map((action, i) => action ? <button key={action.label} tabIndex={-1}
        role={action.checked === undefined ? "menuitem" : "menuitemcheckbox"} aria-checked={action.checked}
        disabled={action.disabled} onClick={() => { close(); action.onSelect(); }}>
        <span>{action.checked !== undefined && <span className="action-menu-check" aria-hidden>{action.checked ? "✓" : ""}</span>}{action.label}</span>
        {action.shortcut && <kbd>{action.shortcut}</kbd>}
      </button> : <div key={`separator-${i}`} role="separator" />)}
    </div>, document.body)}
  </>;
}
