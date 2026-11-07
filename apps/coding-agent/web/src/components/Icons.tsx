/** Small inline SVG icons for the trees. Stroke-based, 14px, colour from CSS (currentColor). */
import type { ReactNode } from "react";

const base = { width: 14, height: 14, viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", strokeWidth: 1.4,
  strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };

const PATHS: Record<string, ReactNode> = {
  directory: <path d="M1.8 4.2c0-.7.5-1.2 1.2-1.2h3l1.4 1.6H13c.7 0 1.2.5 1.2 1.2v6c0 .7-.5 1.2-1.2 1.2H3c-.7 0-1.2-.5-1.2-1.2z" />,
  repo: <><circle cx="4.5" cy="3.5" r="1.4" /><circle cx="4.5" cy="12.5" r="1.4" /><circle cx="11.5" cy="6" r="1.4" /><path d="M4.5 4.9v6.2M11.5 7.4c0 2.4-3.2 2-6 3.6" /></>,
  notebook: <><rect x="3" y="2" width="10" height="12" rx="1.5" /><path d="M6 5.5h4M6 8h4M6 10.5h2.5" /></>,
  file: <><path d="M4 2h5l3 3v8.2c0 .4-.4.8-.8.8H4.8c-.4 0-.8-.4-.8-.8z" /><path d="M9 2v3h3" /></>,
  library: <><rect x="2.5" y="3" width="3" height="10" rx=".6" /><rect x="6.8" y="3" width="3" height="10" rx=".6" /><path d="M11.7 4.2l2 .6-2.2 8-2-.6z" /></>,
  catalog: <><ellipse cx="8" cy="4" rx="5" ry="2" /><path d="M3 4v8c0 1.1 2.2 2 5 2s5-.9 5-2V4M3 8c0 1.1 2.2 2 5 2s5-.9 5-2" /></>,
  schema: <><rect x="2" y="2.5" width="12" height="11" rx="1.5" /><path d="M2 6.2h12M6.3 6.2v7.3" /></>,
  table: <><rect x="2" y="3" width="12" height="10" rx="1.2" /><path d="M2 6.5h12M2 9.8h12M6.5 3v10" /></>,
};

export function Icon({ kind }: { kind: string }) {
  return <svg {...base}>{PATHS[kind] ?? PATHS.file}</svg>;
}

/** A crisp close mark. An SVG, not the "×" character: a font glyph sits high in its em box and
 *  reads as misaligned next to a label, however carefully the button is centred. */
export function CloseIcon({ size = 10 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor"
      strokeWidth={1.9} strokeLinecap="round" aria-hidden="true" focusable="false">
      <path d="M4 4l8 8M12 4l-8 8" />
    </svg>
  );
}
