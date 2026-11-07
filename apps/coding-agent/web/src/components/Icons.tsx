/** The icon set: one geometry, one grid, one stroke.
 *
 * Every icon is a 24×24 viewBox drawn at 16px (14px in dense trees), stroked at 1.8 in
 * `currentColor`, with round caps and joins — the same convention as the reference design system,
 * which inlines the Lucide subset. Two consequences worth stating because they are easy to break:
 *
 * 1. **No text glyphs.** `⟳`, `▤`, `✓`, `×` are characters, not icons: they are sized by the font,
 *    centred by the font's em box (which sits high), and render differently on every platform. A
 *    glyph cannot be optically centred, cannot match a stroke weight, and cannot align to a grid.
 * 2. **One stroke weight everywhere.** Mixing 1.4 and 1.9 makes a toolbar look assembled from parts.
 *    If an icon needs emphasis, change its colour or its size, not its stroke.
 *
 * An icon never appears alone without a name: every button that uses one passes an `aria-label` or
 * a visible word. The `<svg>` is always `aria-hidden`, because the label lives on the control.
 */
import type { ReactNode } from "react";

interface IconProps {
  /** Visual size in px. 16 is the default; 14 for dense rows, 20 for a lone control. */
  size?: number;
  /** Extra class for colour or positioning. */
  className?: string;
}

function Svg({ size = 16, className = "", children }: IconProps & { children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={`icon${className ? ` ${className}` : ""}`}
    >
      {children}
    </svg>
  );
}

/** The product mark: a split pane, the same idea as the brand. Drawn so it holds its weight at
 *  11px inside an avatar and at 13px in the top bar without being a font character. */
export const Mark = (p: IconProps) => (
  <Svg {...p}>
    <rect x="3.5" y="3.5" width="17" height="17" rx="3" />
    <path d="M12 3.5v17" />
    <path d="M3.5 12h8.5" />
  </Svg>
);

/* ---------- chrome: panels and layout ---------- */

/** Left panel. Two panes, left one filled — reads as "the sidebar is on" at 16px. */
export const PanelLeft = (p: IconProps) => (
  <Svg {...p}>
    <rect x="3" y="4" width="18" height="16" rx="2" />
    <path d="M9 4v16" />
    <path d="M3 6a2 2 0 0 1 2-2h4v16H5a2 2 0 0 1-2-2z" fill="currentColor" stroke="none" opacity="0.32" />
  </Svg>
);

/** Right panel. Mirrors PanelLeft exactly, so the pair reads as a pair. */
export const PanelRight = (p: IconProps) => (
  <Svg {...p}>
    <rect x="3" y="4" width="18" height="16" rx="2" />
    <path d="M15 4v16" />
    <path d="M15 4h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-4z" fill="currentColor" stroke="none" opacity="0.32" />
  </Svg>
);

/** Layout menu: a shell with a header bar and zones — deliberately unlike the panel toggles,
 *  which are filled. A menu is a command; a toggle is a state. They must not look the same. */
export const LayoutGrid = (p: IconProps) => (
  <Svg {...p}>
    <rect x="3" y="4" width="18" height="16" rx="2" />
    <path d="M3 9h18" />
    <path d="M10 9v11" />
  </Svg>
);

/** Refresh: a circular arrow. Used for "re-read this from the server". */
export const Refresh = (p: IconProps) => (
  <Svg {...p}>
    <path d="M20 11a8 8 0 1 0-2.3 5.7" />
    <path d="M20 5v6h-6" />
  </Svg>
);

/** Search: the magnifier. */
export const Search = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="10.5" cy="10.5" r="6.5" />
    <path d="m16 16 4.5 4.5" />
  </Svg>
);

/** Command key. Drawn, not typed: the ⌘ character renders as a different shape per platform. */
export const CommandKey = (p: IconProps) => (
  <Svg {...p}>
    <path d="M9 6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3z" />
  </Svg>
);

/* ---------- disclosure ---------- */

/** Disclosure caret, pointing right when closed. Rotated 90° by CSS when open, so one icon serves both. */
export const ChevronRight = (p: IconProps) => (
  <Svg {...p}>
    <path d="m9 5 7 7-7 7" />
  </Svg>
);

export const ChevronLeft = (p: IconProps) => (
  <Svg {...p}>
    <path d="m15 5-7 7 7 7" />
  </Svg>
);

export const ChevronDown = (p: IconProps) => (
  <Svg {...p}>
    <path d="m5 9 7 7 7-7" />
  </Svg>
);

/* ---------- status ---------- */

/** Completed. A check, not a "✓" character, so it centres in its circle. */
export const Check = (p: IconProps) => (
  <Svg {...p}>
    <path d="m4.5 12.5 5 5L19.5 7" />
  </Svg>
);

/** Not verified / needs attention. */
export const Alert = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 8v5" />
    <circle cx="12" cy="16.5" r="0.6" fill="currentColor" stroke="none" />
    <path d="M12 3.5 21 20H3z" />
  </Svg>
);

/** Running. A filled disc; the pulse is CSS, not a different icon. */
export const Dot = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="4.5" fill="currentColor" stroke="none" />
  </Svg>
);

/** Pending. An open ring, the deliberate opposite of Dot. */
export const Ring = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="4.5" />
  </Svg>
);

/** Stopped. */
export const Square = (p: IconProps) => (
  <Svg {...p}>
    <rect x="7" y="7" width="10" height="10" rx="1.6" fill="currentColor" stroke="none" />
  </Svg>
);

/** Save. A floppy is the icon everyone still reads as "save", even though nobody owns one. */
export const Save = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5 3h11l3 3v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z" />
    <path d="M8 3v6h7V3" />
    <rect x="8" y="13" width="8" height="7" rx="1" />
  </Svg>
);

/** Locked. Used for "read-only", not for "secure", so it is a padlock on a document. */
export const Lock = (p: IconProps) => (
  <Svg {...p}>
    <rect x="5" y="10" width="14" height="10" rx="2" />
    <path d="M8 10V7a4 4 0 0 1 8 0v3" />
  </Svg>
);

/** Warning. A triangle with a bang: distinguishable from Alert at 13px by its outline shape. */
export const Warning = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 3.8 21 19.5H3z" />
    <path d="M12 9.5v4.2" />
    <circle cx="12" cy="16.6" r="0.65" fill="currentColor" stroke="none" />
  </Svg>
);

/* ---------- objects ---------- */

/** A conversation. */
export const Chat = (p: IconProps) => (
  <Svg {...p}>
    <path d="M21 11.5a8 8 0 0 1-8 8H8l-4 2.5V11.5a8 8 0 0 1 8-8h1a8 8 0 0 1 8 8z" />
  </Svg>
);

export const Notebook = (p: IconProps) => (
  <Svg {...p}>
    <rect x="5" y="3" width="14" height="18" rx="2" />
    <path d="M9 8h6M9 12h6M9 16h3.5" />
  </Svg>
);

export const FileIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M6 3h7l5 5v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z" />
    <path d="M13 3v5h5" />
  </Svg>
);

export const Folder = (p: IconProps) => (
  <Svg {...p}>
    <path d="M3 6.5A1.5 1.5 0 0 1 4.5 5h5l2 2.5h7A1.5 1.5 0 0 1 20 9v9a1.5 1.5 0 0 1-1.5 1.5h-14A1.5 1.5 0 0 1 3 18z" />
  </Svg>
);

export const Table = (p: IconProps) => (
  <Svg {...p}>
    <rect x="3" y="4" width="18" height="16" rx="2" />
    <path d="M3 9h18M3 14.5h18M9.5 9v11" />
  </Svg>
);

export const Database = (p: IconProps) => (
  <Svg {...p}>
    <ellipse cx="12" cy="6" rx="7.5" ry="3" />
    <path d="M4.5 6v12c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3V6" />
    <path d="M4.5 12c0 1.7 3.4 3 7.5 3s7.5-1.3 7.5-3" />
  </Svg>
);

export const Schema = (p: IconProps) => (
  <Svg {...p}>
    <rect x="3" y="4" width="18" height="16" rx="2" />
    <path d="M3 9.5h18M9.5 9.5V20" />
  </Svg>
);

export const Repo = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="7" cy="5.5" r="2.2" />
    <circle cx="7" cy="18.5" r="2.2" />
    <circle cx="17" cy="9" r="2.2" />
    <path d="M7 7.7v8.6" />
    <path d="M17 11.2c0 3.6-4.6 3-8 5.2" />
  </Svg>
);

/* ---------- actions ---------- */

/** New. A plus, drawn. */
export const Plus = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 5v14M5 12h14" />
  </Svg>
);

/** Close. Two strokes on the diagonals, so it optically centres. */
export const Close = (p: IconProps) => (
  <Svg {...p} size={p.size ?? 12}>
    <path d="M5 5l14 14M19 5L5 19" />
  </Svg>
);

/** Stop generating. */
export const Stop = (p: IconProps) => (
  <Svg {...p}>
    <rect x="6" y="6" width="12" height="12" rx="2" />
  </Svg>
);

/** Send. An arrow leaving, which is what sending is. */
export const Send = (p: IconProps) => (
  <Svg {...p}>
    <path d="M5 12h13M12.5 6l6 6-6 6" />
  </Svg>
);

/* ---------- theme ---------- */

export const Monitor = (p: IconProps) => (
  <Svg {...p}>
    <rect x="3" y="4" width="18" height="12" rx="2" />
    <path d="M9 20h6M12 16v4" />
  </Svg>
);

export const Sun = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="4.2" />
    <path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4 6 18M18 6l1.4-1.4" />
  </Svg>
);

export const Moon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M20 14.5A8.5 8.5 0 0 1 9.5 4a8.5 8.5 0 1 0 10.5 10.5z" />
  </Svg>
);

/* ---------- scenario cards ---------- */

export const Sparkle = (p: IconProps) => (
  <Svg {...p}>
    <path d="M12 3.5 13.9 9l5.6 1.9-5.6 1.9L12 18.4l-1.9-5.6L4.5 10.9 10.1 9z" />
  </Svg>
);

export const Clock = (p: IconProps) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 7.5V12l3.2 2" />
  </Svg>
);

export const Layers = (p: IconProps) => (
  <Svg {...p}>
    <path d="m12 3 9 5-9 5-9-5z" />
    <path d="m3 13 9 5 9-5" />
  </Svg>
);

export const ListIcon = (p: IconProps) => (
  <Svg {...p}>
    <path d="M8 6.5h12M8 12h12M8 17.5h12M4 6.5h.01M4 12h.01M4 17.5h.01" />
  </Svg>
);

export const Bug = (p: IconProps) => (
  <Svg {...p}>
    <rect x="8" y="6" width="8" height="12" rx="4" />
    <path d="M8 10H4.5M8 14H4.5M16 10h3.5M16 14h3.5M9.5 4 8 6M14.5 4 16 6" />
  </Svg>
);

/** A registry so a data table can name an icon instead of embedding a glyph. */
export const ICONS = {
  panelLeft: PanelLeft, panelRight: PanelRight, layout: LayoutGrid, refresh: Refresh, chat: Chat,
  search: Search, command: CommandKey, chevron: ChevronRight, check: Check, alert: Alert,
  dot: Dot, ring: Ring, square: Square, notebook: Notebook, file: FileIcon, folder: Folder,
  table: Table, database: Database, schema: Schema, repo: Repo, plus: Plus, close: Close,
  stop: Stop, send: Send, monitor: Monitor, sun: Sun, moon: Moon, sparkle: Sparkle,
  save: Save, lock: Lock, warning: Warning,
  clock: Clock, layers: Layers, list: ListIcon, bug: Bug,
} as const;

export type IconName = keyof typeof ICONS;

/* ---------- compatibility: the tree API ----------
 * `Icon kind="notebook"` predates this set and is used by four call sites. It now resolves to the
 * real icon rather than its own 16px 1.4-stroke drawing, so there is exactly one geometry in the
 * app. Kept as a named export so the call sites do not churn. */
const BY_KIND: Record<string, (p: IconProps) => ReactNode> = {
  directory: Folder, folder: Folder, repo: Repo, notebook: Notebook, file: FileIcon,
  library: Database, catalog: Database, schema: Schema, table: Table,
};

export function Icon({ kind, size = 14 }: { kind: string; size?: number }) {
  const C = BY_KIND[kind] ?? FileIcon;
  return <C size={size} />;
}

/** Kept for DocTabs; now shares the 24-grid and the 1.8 stroke with everything else. */
export function CloseIcon({ size = 12 }: { size?: number }) {
  return <Close size={size} />;
}
