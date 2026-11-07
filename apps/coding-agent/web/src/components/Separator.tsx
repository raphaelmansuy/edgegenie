/** The handle between two zones: pointer, keyboard and screen reader, all on one element.
 *
 * A resize affordance is only a feature if it is discoverable and reachable. So this is a real
 * `role="separator"` with a value, not a decorative div: it takes focus, announces the zone it
 * controls and its width in pixels, and answers the arrow keys. (specs/001-perfect-shell SH-A1..A6.)
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { KEY_STEP, KEY_STEP_COARSE, type Zone } from "../domain/layout";

export function Separator({ zone, width, min, max, label, onResize, onReset }: {
  zone: Zone;
  width: number;
  min: number;
  max: number;
  label: string;
  /** New width in px. The caller clamps; this component only reports intent. */
  onResize: (px: number) => void;
  onReset: () => void;
}) {
  const [dragging, setDragging] = useState(false);
  const startX = useRef(0);
  const startWidth = useRef(0);
  const frame = useRef(0);
  const pending = useRef<number | null>(null);

  // Coalesce to one resize per frame: a 60 Hz pointer stream must not cause 60 layout passes.
  const schedule = useCallback((px: number) => {
    pending.current = px;
    if (frame.current) return;
    frame.current = window.requestAnimationFrame(() => {
      frame.current = 0;
      if (pending.current !== null) onResize(pending.current);
    });
  }, [onResize]);

  useEffect(() => () => { if (frame.current) window.cancelAnimationFrame(frame.current); }, []);

  const onPointerDown = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    e.preventDefault();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    startX.current = e.clientX;
    startWidth.current = width;
    setDragging(true);
  };

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragging) return;
    const delta = zone === "rail" ? e.clientX - startX.current : startX.current - e.clientX;
    schedule(startWidth.current + delta);
  };

  const end = (e: React.PointerEvent<HTMLDivElement>) => {
    if (!dragging) return;
    setDragging(false);
    try { (e.currentTarget as HTMLElement).releasePointerCapture(e.pointerId); } catch { /* already gone */ }
  };

  return (
    <div
      className={`separator${dragging ? " is-dragging" : ""}`}
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuenow={Math.round(width)}
      aria-valuemin={min}
      aria-valuemax={Number.isFinite(max) ? Math.round(max) : undefined}
      tabIndex={0}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={end}
      onPointerCancel={end}
      onDoubleClick={onReset}
      onKeyDown={(e) => {
        const coarse = e.shiftKey;
        const step = coarse ? KEY_STEP_COARSE : KEY_STEP;
        // ArrowLeft always narrows from the left edge of the zone being resized; for the inspector,
        // whose handle sits on its left, ArrowLeft widens. So the sign follows the zone.
        const sign = zone === "rail" ? 1 : -1;
        if (e.key === "ArrowRight") { e.preventDefault(); onResize(width + step * sign); }
        else if (e.key === "ArrowLeft") { e.preventDefault(); onResize(width - step * sign); }
        else if (e.key === "Home") { e.preventDefault(); onReset(); }
      }}
    />
  );
}
