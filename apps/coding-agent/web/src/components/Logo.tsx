/** The OpenGenie identity: the mark, the wordmark, and the tile.
 *
 * The mark is an **open ring with a spark in the gap**: "Open" is the ring that does not close, and
 * "Genie" is the spark. Two strokes and one fill, no letterforms — so it holds at 16px in a tab and at
 * 48px on the home screen without a second, detailed variant.
 *
 * The glyph is stroked in `currentColor` like every other icon, and the tile chooses the colour. That
 * is what keeps it legible in both themes: the accent inverts (dark blue on paper, light blue on
 * near-black), and the glyph follows it, exactly as the rest of the icon set does.
 */
import type { ReactNode } from "react";

interface LogoProps {
  /** Height and width of the glyph in px. */
  size?: number;
  className?: string;
}

/** The glyph alone, transparent. For the top bar's tile, the home hero and the favicon. */
export function LogoMark({ size = 20, className = "" }: LogoProps) {
  return (
    <svg
      width={size} height={size} viewBox="0 0 24 24" fill="none"
      aria-hidden="true" focusable="false" className={`logo-mark${className ? ` ${className}` : ""}`}
    >
      {/* The ring, open between -60° and -30° (top right). One arc, so the gap is exact. */}
      <path
        d="M18.93 8A8 8 0 1 1 16 5.07"
        stroke="currentColor" strokeWidth={2.15} strokeLinecap="round"
      />
      {/* The spark: a four-point star, filled, sitting just outside the gap it made. */}
      <path
        d="M18.9 2.1l.82 2.18 2.18.82-2.18.82-.82 2.18-.82-2.18L15.9 5.1l2.18-.82z"
        fill="currentColor"
      />
    </svg>
  );
}

/** The glyph on a rounded tile — the app icon. `tone="ink"` for dense chrome, `accent` for the hero. */
export function LogoBadge({ size = 22, tone = "accent", className = "" }: LogoProps & { tone?: "accent" | "ink" }) {
  return (
    <span className={`logo-badge is-${tone}${className ? ` ${className}` : ""}`}
      style={{ width: size, height: size, borderRadius: Math.round(size * 0.29) }} aria-hidden>
      <LogoMark size={Math.round(size * 0.66)} />
    </span>
  );
}

/** "Open" in ink and "Genie" in the accent: the name reads as one word but the brand stays visible
 *  when the whole thing is scanned at a glance. `srLabel` keeps it one word for assistive tech. */
export function Wordmark({ children }: { children?: ReactNode }) {
  return (
    <span className="wordmark">
      <span className="wordmark-a">Open</span>
      <span className="wordmark-b">Genie</span>
      {children}
    </span>
  );
}
