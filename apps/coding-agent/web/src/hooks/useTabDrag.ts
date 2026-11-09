import { useEffect, useRef, useState, type PointerEvent as ReactPointerEvent, type RefObject } from "react";

interface Gesture {
  id: string; pointer: number; element: HTMLElement;
  startX: number; startY: number; x: number; y: number;
  touch: boolean; scrolling: boolean; dragging: boolean; index: number;
}

/** One pointer lifecycle for mouse, pen and touch. Only release commits; all exits clean up. */
export function useTabDrag(strip: RefObject<HTMLDivElement | null>, ids: string[], onMove: (id: string, index: number) => void) {
  const [drag, setDrag] = useState<{ id: string; index: number; marker: number } | null>(null);
  const gesture = useRef<Gesture | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const suppressedUntil = useRef(0);
  const live = useRef({ ids, onMove });
  live.current = { ids, onMove };

  function clear() {
    clearTimeout(timer.current);
    const g = gesture.current;
    gesture.current = null;
    if (g?.element.hasPointerCapture(g.pointer)) g.element.releasePointerCapture(g.pointer);
    setDrag(null);
  }
  function update() {
    const g = gesture.current, el = strip.current;
    if (!g?.dragging || !el) return;
    const others = Array.from(el.querySelectorAll<HTMLElement>("[data-tab-id]")).filter((t) => t.dataset.tabId !== g.id);
    const index = others.filter((t) => {
      const r = t.getBoundingClientRect();
      return g.x > r.left + r.width / 2;
    }).length;
    const box = el.getBoundingClientRect();
    const edge = others[index]?.getBoundingClientRect().left ?? others.at(-1)?.getBoundingClientRect().right ?? box.left;
    const marker = Math.max(2, Math.min(el.clientWidth - 3, edge - box.left));
    g.index = index;
    setDrag((prev) => prev?.id === g.id && prev.index === index && prev.marker === marker ? prev : { id: g.id, index, marker });
  }
  function activate() {
    const g = gesture.current;
    if (!g) return;
    g.dragging = true;
    suppressedUntil.current = Infinity;
    update();
  }
  function cancel() {
    if (gesture.current?.dragging || gesture.current?.scrolling) suppressedUntil.current = performance.now() + 400;
    clear();
  }

  useEffect(() => {
    if (!drag) return;
    let frame = 0, last = 0;
    const tick = (now: number) => {
      const g = gesture.current, el = strip.current;
      if (!g || !el) return;
      const box = el.getBoundingClientRect();
      if (g.y >= box.top && g.y <= box.bottom) {
        const edge = Math.min(44, box.width / 4);
        const speed = g.x < box.left + edge ? -Math.min(1, (box.left + edge - g.x) / edge)
          : g.x > box.right - edge ? Math.min(1, (g.x - box.right + edge) / edge) : 0;
        el.scrollLeft += speed * Math.min(32, last ? now - last : 16) * 0.65;
        update();
      }
      last = now;
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [Boolean(drag)]);

  useEffect(() => {
    if (gesture.current && !ids.includes(gesture.current.id)) cancel();
  }, [ids.join("\u0000")]);

  useEffect(() => {
    const escape = (e: KeyboardEvent) => {
      if (e.key === "Escape" && gesture.current) { e.preventDefault(); e.stopPropagation(); cancel(); }
    };
    window.addEventListener("keydown", escape, true);
    window.addEventListener("blur", cancel);
    return () => {
      clearTimeout(timer.current);
      const g = gesture.current;
      gesture.current = null;
      if (g?.element.hasPointerCapture(g.pointer)) g.element.releasePointerCapture(g.pointer);
      window.removeEventListener("keydown", escape, true);
      window.removeEventListener("blur", cancel);
    };
  }, []);

  return {
    drag,
    suppressClick: () => performance.now() < suppressedUntil.current,
    start: (e: ReactPointerEvent<HTMLElement>, id: string) => {
      if (gesture.current || !e.isPrimary || e.button !== 0 || (e.target as HTMLElement).closest("button")) return;
      suppressedUntil.current = 0; // A fresh press is never the synthetic click following a drag.
      if (ids.length < 2) return;
      const touch = e.pointerType === "touch";
      gesture.current = { id, pointer: e.pointerId, element: e.currentTarget,
        startX: e.clientX, startY: e.clientY, x: e.clientX, y: e.clientY,
        touch, scrolling: false, dragging: false, index: ids.indexOf(id) };
      e.currentTarget.setPointerCapture(e.pointerId);
      if (touch) timer.current = setTimeout(activate, 240);
    },
    move: (e: ReactPointerEvent<HTMLElement>) => {
      const g = gesture.current;
      if (!g || g.pointer !== e.pointerId) return;
      const dx = e.clientX - g.x;
      g.x = e.clientX; g.y = e.clientY;
      if (!g.dragging && Math.hypot(g.x - g.startX, g.y - g.startY) >= 6) {
        clearTimeout(timer.current);
        if (g.touch) g.scrolling = true;
        else activate();
      }
      if (g.scrolling && strip.current) { strip.current.scrollLeft -= dx; suppressedUntil.current = Infinity; }
      if (g.dragging || g.scrolling) e.preventDefault();
      update();
    },
    end: (e: ReactPointerEvent<HTMLElement>) => {
      const g = gesture.current, el = strip.current;
      if (!g || g.pointer !== e.pointerId || !el) return;
      const box = el.getBoundingClientRect();
      if (g.dragging && e.clientX >= box.left && e.clientX <= box.right && e.clientY >= box.top && e.clientY <= box.bottom
        && live.current.ids.includes(g.id)) live.current.onMove(g.id, g.index);
      cancel();
    },
    cancel,
  };
}
