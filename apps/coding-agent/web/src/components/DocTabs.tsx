/** Ordered document navigation. App owns identity/binding; this strip owns geometry and gestures. */
import { useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";
import { createPortal } from "react-dom";
import { ChevronDown, ChevronLeft, ChevronRight, CloseIcon, FileIcon, More, Notebook, Table } from "./Icons";
import { docTabId } from "../domain/tabs";
import { display } from "../domain/keys";
import { useTabDrag } from "../hooks/useTabDrag";

export interface DocTab { id: string; name: string; kind: string; ref: string }
interface Props {
  docs: DocTab[]; active: string; dirtyIds: ReadonlySet<string>;
  onSelect: (id: string) => void;
  onClose: (id: string) => void;
  onCloseMany: (ids: string[]) => void;
  onMove: (id: string, index: number) => void;
  onReopen: () => void;
  canReopen: boolean;
}
const tabIcon = (kind: string) => kind === "table" ? <Table size={14} /> : kind === "file" ? <FileIcon size={14} /> : <Notebook size={14} />;

export function DocTabs({ docs, active, dirtyIds, onSelect, onClose, onCloseMany, onMove, onReopen, canReopen }: Props) {
  const strip = useRef<HTMLDivElement>(null);
  const pickerButton = useRef<HTMLButtonElement>(null);
  const actionsButton = useRef<HTMLButtonElement>(null);
  const popupReturn = useRef<HTMLElement | null>(null);
  const popover = useRef<HTMLDivElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const [overflow, setOverflow] = useState({ left: false, right: false, hidden: 0 });
  const [popup, setPopup] = useState<{ kind: "picker" | "menu"; id?: string; x: number; y: number } | null>(null);
  const [query, setQuery] = useState("");
  const [announcement, announce] = useState("");
  const ids = docs.map((d) => d.id);
  const orderedIds = JSON.stringify(ids);
  const activeRef = useRef(active);
  activeRef.current = active;
  const move = (id: string, index: number) => {
    const to = Math.max(0, Math.min(docs.length - 1, index));
    if (ids.indexOf(id) === to) return;
    onMove(id, to);
    announce(`${docs.find((d) => d.id === id)?.name} moved to position ${to + 1} of ${docs.length}`);
  };
  const gesture = useTabDrag(strip, ids, move);

  function measure() {
    const s = strip.current;
    if (!s) return;
    const box = s.getBoundingClientRect();
    const hidden = Array.from(s.querySelectorAll<HTMLElement>("[data-tab]")).filter((el) => {
      const r = el.getBoundingClientRect();
      return r.left < box.left - 1 || r.right > box.right + 1;
    }).length;
    const next = { left: s.scrollLeft > 1, right: s.scrollLeft + s.clientWidth < s.scrollWidth - 1, hidden };
    setOverflow((prev) => prev.left === next.left && prev.right === next.right && prev.hidden === hidden ? prev : next);
  }
  function reveal(id = activeRef.current) {
    const s = strip.current, tab = document.getElementById(docTabId(id));
    if (!s || !tab) { measure(); return; }
    const box = s.getBoundingClientRect(), r = tab.getBoundingClientRect();
    if (r.width > box.width - 12 || r.left < box.left + 6) s.scrollLeft += r.left - (box.left + 6);
    else if (r.right > box.right - 6) s.scrollLeft += r.right - (box.right - 6);
    measure();
  }
  function activate(id: string) {
    onSelect(id);
    // React can bail out when the already-active tab is chosen. Explicitly reveal it even then.
    reveal(id);
  }
  useLayoutEffect(() => { reveal(); }, [active, orderedIds]);
  useEffect(() => {
    const s = strip.current;
    if (!s) return;
    const observer = new ResizeObserver(() => reveal());
    observer.observe(s);
    for (const tab of s.children) observer.observe(tab);
    const wheel = (e: WheelEvent) => {
      if (e.ctrlKey || e.metaKey || s.scrollWidth <= s.clientWidth) return;
      let delta = Math.abs(e.deltaX) > Math.abs(e.deltaY) ? e.deltaX : e.deltaY;
      if (e.deltaMode === 1) delta *= 16;
      if (e.deltaMode === 2) delta *= s.clientWidth;
      if (!delta) return;
      e.preventDefault();
      s.scrollLeft += delta;
    };
    s.addEventListener("wheel", wheel, { passive: false });
    return () => { observer.disconnect(); s.removeEventListener("wheel", wheel); };
  }, [orderedIds]);

  const closePopup = (restore = true) => {
    if (restore) {
      const target = popupReturn.current?.isConnected ? popupReturn.current : pickerButton.current;
      target?.focus({ preventScroll: true });
    }
    setPopup(null);
  };
  useEffect(() => {
    if (!popup) return;
    if (popup.kind === "picker") search.current?.focus();
    else popover.current?.querySelector<HTMLButtonElement>("button:not(:disabled)")?.focus();
    const outside = (e: PointerEvent) => {
      if (!popover.current?.contains(e.target as Node) && !pickerButton.current?.contains(e.target as Node)
        && !actionsButton.current?.contains(e.target as Node)) setPopup(null);
    };
    const resize = () => setPopup(null);
    const focusOut = (e: FocusEvent) => {
      if (!popover.current?.contains(e.target as Node) && e.target !== pickerButton.current && e.target !== actionsButton.current) setPopup(null);
    };
    document.addEventListener("pointerdown", outside);
    document.addEventListener("focusin", focusOut);
    window.addEventListener("resize", resize);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("focusin", focusOut); window.removeEventListener("resize", resize); };
  }, [popup]);
  useEffect(() => { if (popup?.id && !ids.includes(popup.id)) setPopup(null); }, [orderedIds, popup?.id]);

  function openPopup(kind: "picker" | "menu", id?: string, x?: number, y?: number, returnFocus?: HTMLElement) {
    const anchor = pickerButton.current?.getBoundingClientRect();
    const width = Math.min(kind === "picker" ? 380 : 240, window.innerWidth - 16);
    setQuery("");
    popupReturn.current = returnFocus ?? (kind === "menu" && id ? document.getElementById(docTabId(id)) : pickerButton.current);
    setPopup({ kind, id,
      x: Math.max(8, Math.min(x ?? (anchor?.right ?? window.innerWidth) - width, window.innerWidth - width - 8)),
      y: Math.max(8, Math.min(y ?? anchor?.bottom ?? 100, window.innerHeight - (kind === "picker" ? 320 : 300))) });
  }
  function popupKeys(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); closePopup(); return; }
    // Leave global editor shortcuts to the shell only after dismissing this transient.
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "w") { e.preventDefault(); e.stopPropagation(); return; }
    const buttons = Array.from(popover.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)") ?? []);
    const at = buttons.indexOf(document.activeElement as HTMLButtonElement);
    const inSearch = e.target === search.current;
    if (e.key === "ArrowDown" || e.key === "ArrowUp" || (!inSearch && (e.key === "Home" || e.key === "End"))) {
      e.preventDefault();
      const next = e.key === "Home" ? 0 : e.key === "End" ? buttons.length - 1
        : at < 0 ? (e.key === "ArrowDown" ? 0 : buttons.length - 1) : (at + (e.key === "ArrowDown" ? 1 : -1) + buttons.length) % buttons.length;
      buttons[next]?.focus();
    }
  }
  function tabKeys(e: KeyboardEvent<HTMLDivElement>, id: string) {
    if (e.target !== e.currentTarget) return;
    const at = ids.indexOf(id);
    if (e.altKey && e.shiftKey && (e.key === "ArrowLeft" || e.key === "ArrowRight")) {
      e.preventDefault(); e.stopPropagation(); move(id, at + (e.key === "ArrowRight" ? 1 : -1));
      requestAnimationFrame(() => reveal(id)); return;
    }
    if (e.key === "ContextMenu" || (e.shiftKey && e.key === "F10")) {
      e.preventDefault(); const r = e.currentTarget.getBoundingClientRect(); openPopup("menu", id, r.left, r.bottom); return;
    }
    if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
    if (["ArrowRight", "ArrowLeft", "Home", "End"].includes(e.key)) {
      e.preventDefault();
      const to = e.key === "Home" ? 0 : e.key === "End" ? ids.length - 1 : (at + (e.key === "ArrowRight" ? 1 : -1) + ids.length) % ids.length;
      activate(ids[to]);
      requestAnimationFrame(() => document.getElementById(docTabId(ids[to]))?.focus({ preventScroll: true }));
    } else if (e.key === "Enter" || e.key === " ") { e.preventDefault(); activate(id); }
    else if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); onClose(id); }
  }

  if (!docs.length) return null;
  const q = query.trim().toLocaleLowerCase();
  const found = docs.filter((d) => `${d.name} ${d.ref}`.toLocaleLowerCase().includes(q));
  const menuAt = docs.findIndex((d) => d.id === popup?.id);
  const menuDoc = docs[menuAt];
  const run = (action: () => void) => { closePopup(); action(); };
  const scroll = (direction: number) => {
    const s = strip.current;
    s?.scrollBy({ left: direction * Math.max(100, s.clientWidth * 0.75), behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" });
  };
  return (
    <div className={`doc-tabs-wrap${gesture.drag ? " is-dragging" : ""}`}>
      <div className="doc-tabs" role="tablist" aria-label="Open items" aria-orientation="horizontal" ref={strip} onScroll={measure}>
        {docs.map((d, index) => {
          const duplicate = docs.some((other) => other.id !== d.id && other.name === d.name);
          return <div key={d.id} id={docTabId(d.id)} data-tab data-tab-id={d.id}
            className={`doc-tab${gesture.drag?.id === d.id ? " is-drag-source" : ""}`} role="tab"
            aria-selected={active === d.id} aria-controls="doc-panel" aria-description={`${d.ref}${dirtyIds.has(d.id) ? ", unsaved changes" : ""}. Drag to reorder, or use Alt+Shift+Left or Right. Shift+F10 for tab actions.`}
            tabIndex={active === d.id || (!ids.includes(active) && index === 0) ? 0 : -1}
            onClick={(e) => { if (gesture.suppressClick()) { e.preventDefault(); return; } activate(d.id); }} title={d.ref}
            onPointerDown={(e) => gesture.start(e, d.id)} onPointerMove={gesture.move} onPointerUp={gesture.end}
            onPointerCancel={gesture.cancel} onLostPointerCapture={gesture.cancel} onDragStart={(e) => e.preventDefault()}
            onAuxClick={(e) => { if (e.button === 1) { e.preventDefault(); onClose(d.id); } }}
            onMouseDown={(e) => { if (e.button === 1) e.preventDefault(); }}
            onContextMenu={(e) => { e.preventDefault(); if (!gesture.drag) openPopup("menu", d.id, e.clientX, e.clientY); }}
            onKeyDown={(e) => tabKeys(e, d.id)}>
            <span className="tab-icon" aria-hidden>{tabIcon(d.kind)}</span>
            <span className="doc-tab-label">{d.name}</span>
            {duplicate && <span className="doc-tab-parent">{d.ref.slice(0, d.ref.lastIndexOf(d.kind === "table" ? "." : "/"))}</span>}
            {dirtyIds.has(d.id) && <span className="doc-tab-dirty" aria-label="Unsaved changes" title="Unsaved changes" />}
            <button className="doc-close" tabIndex={-1} aria-label={`Close ${d.name}`} title={`Close ${d.name} (${display("mod+w")})`}
              onPointerDown={(e) => e.stopPropagation()} onClick={(e) => { e.stopPropagation(); onClose(d.id); }}><CloseIcon /></button>
          </div>;
        })}
      </div>
      {gesture.drag && <span className="tab-drop-marker" aria-hidden style={{ left: gesture.drag.marker }} />}
      <div className="doc-tabs-controls" role="group" aria-label="Document navigation">
        <button className="tab-control tab-scroll" aria-label="Scroll tabs left" title="Scroll tabs left" disabled={!overflow.left} onClick={() => scroll(-1)}><ChevronLeft size={15} /></button>
        <button className="tab-control tab-scroll" aria-label="Scroll tabs right" title="Scroll tabs right" disabled={!overflow.right} onClick={() => scroll(1)}><ChevronRight size={15} /></button>
        <button ref={actionsButton} className="tab-control" aria-label="Tab actions" aria-haspopup="menu" aria-expanded={popup?.kind === "menu"}
          title="Tab actions — move, close or reopen" onClick={(e) => {
            if (popup?.kind === "menu") { closePopup(); return; }
            const r = e.currentTarget.getBoundingClientRect();
            openPopup("menu", ids.includes(active) ? active : ids[0], r.right - 240, r.bottom, e.currentTarget);
          }}><More size={15} /></button>
        <button className="tab-control tab-picker-trigger" aria-label={`Open documents (${docs.length})`} title="Open documents — search by name or path"
          aria-expanded={popup?.kind === "picker"} aria-haspopup="dialog" ref={pickerButton}
          onClick={() => popup?.kind === "picker" ? closePopup() : openPopup("picker")}>
          <span className="tab-count">{overflow.hidden ? `+${overflow.hidden}` : docs.length}</span><ChevronDown size={14} />
        </button>
      </div>
      <span className="sr-only" role="status" aria-live="polite">{announcement}</span>
      {popup && createPortal(
        <div ref={popover} className={`tab-popover ${popup.kind === "picker" ? "tab-picker" : "tab-menu"}`} style={{ left: popup.x, top: popup.y }}
          role={popup.kind === "picker" ? "dialog" : "menu"} aria-label={popup.kind === "picker" ? "Open documents" : `Tab actions for ${menuDoc?.name ?? "document"}`}
          onKeyDown={popupKeys}>
          {popup.kind === "picker" ? <>
            <div className="tab-picker-heading"><strong>Open documents</strong><span>{docs.length}</span></div>
            <input ref={search} className="tab-picker-search" aria-label="Search open documents" placeholder="Search by name or path…" value={query} onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && found[0]) { e.preventDefault(); run(() => activate(found[0].id)); requestAnimationFrame(() => document.getElementById(docTabId(found[0].id))?.focus({ preventScroll: true })); } }} />
            <div className="tab-picker-results" aria-label="Matching documents">
              {found.map((d) => <button key={d.id} className="tab-picker-row" aria-current={active === d.id ? "true" : undefined}
                onClick={() => { run(() => activate(d.id)); requestAnimationFrame(() => document.getElementById(docTabId(d.id))?.focus({ preventScroll: true })); }}>
                <span aria-hidden>{tabIcon(d.kind)}</span><span className="tab-picker-identity"><strong>{d.name}</strong><small>{d.ref}</small></span>
                {active === d.id && <span className="tab-picker-current">Active</span>}
              </button>)}
              {!found.length && <p className="tab-picker-empty" role="status">No open documents match “{query}”.</p>}
            </div>
            <div className="tab-picker-hint">Drag to reorder · Alt+Shift+← / → to move</div>
          </> : menuDoc && <>
            <div className="tab-menu-title" title={menuDoc.ref}>{menuDoc.name}</div>
            <button role="menuitem" disabled={menuAt === 0} onClick={() => run(() => move(menuDoc.id, menuAt - 1))}>Move left <kbd>Alt+Shift+←</kbd></button>
            <button role="menuitem" disabled={menuAt === docs.length - 1} onClick={() => run(() => move(menuDoc.id, menuAt + 1))}>Move right <kbd>Alt+Shift+→</kbd></button>
            <div role="separator" />
            <button role="menuitem" onClick={() => run(() => onClose(menuDoc.id))}>Close <kbd>{display("mod+w")}</kbd></button>
            <button role="menuitem" disabled={docs.length < 2} onClick={() => run(() => onCloseMany(ids.filter((id) => id !== menuDoc.id)))}>Close others</button>
            <button role="menuitem" disabled={menuAt === docs.length - 1} onClick={() => run(() => onCloseMany(ids.slice(menuAt + 1)))}>Close to the right</button>
            <button role="menuitem" onClick={() => run(() => onCloseMany(ids))}>Close all</button>
            <div role="separator" />
            <button role="menuitem" disabled={!canReopen} onClick={() => run(onReopen)}>Reopen closed tab <kbd>{display("mod+shift+t")}</kbd></button>
          </>}
        </div>, document.body)}
    </div>
  );
}
