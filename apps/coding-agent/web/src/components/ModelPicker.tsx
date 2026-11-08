/** The model picker: one component, three entry points (chip, palette, inspector).
 *
 * A combobox over a listbox with `aria-activedescendant`, because a native `<select>` cannot show a
 * group with a status badge and a "needs a key" remedy (07 §Accessibility contract).
 *
 * What is deliberate here:
 *  - **the trigger is a chip** that keeps its width from the label at first paint, so opening the
 *    popover cannot move the layout (NFR-2 / CLS);
 *  - **every group is always present**, with a count, even at zero matches, so a provider is never
 *    silently absent (U1);
 *  - **an unavailable row has no action**, only a remedy, so it cannot be selected (U7);
 *  - **Enter on a disabled row announces the reason** through `role="status"` (E-29);
 *  - **`esc` returns focus to the trigger** (U5), and reduced motion is honoured.
 */
import { useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { highlight } from "../domain/fuzzy";
import {
  availabilityCopy,
  canChoose,
  freshness,
  GROUP_UNAVAILABLE,
  groupModels,
  label,
  limitsCopy,
  needsKey,
  providerTag,
  searchSummary,
  sourceNotice,
  STATE_COPY,
  type CatalogueResponse,
  type ModelSpec,
} from "../domain/models";
import { Check, ChevronDown, Ring, Warning } from "./Icons";

export interface ModelPickerProps {
  catalogue: CatalogueResponse | null;
  /** The model this session is pinned to. */
  current: string;
  /** Called with the id the user chose. The server decides whether a restart is needed. */
  onChoose: (id: string) => Promise<void>;
  /** Optional: open the key settings for a model that needs one (FR-19). */
  onAddKey?: (provider: string) => void;
  /** Optional: force a catalogue refresh, shown when the list is stale (U10). */
  onRefresh?: () => void;
  /** How the trigger looks: the topbar chip, or a button inside the inspector. */
  variant?: "chip" | "button";
  /** A word before the model name: `model` in a composer, nothing in the top bar (006 MC-7). */
  triggerGlyph?: string;
  label?: string;
  disabled?: boolean;
  /**
   * Controlled open state. The trigger alone is not enough: below 1100px the chip is hidden by CSS,
   * so the palette command and the inspector's "Change model" need a way to open the *same* picker
   * without clicking an invisible element. Supplying this makes those entry points real.
   */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

const POPOVER_WIDTH = 460;
/** The app's top bar is 52px tall; a popover that flips upward must start below it. */
const TOPBAR = 52;

export function ModelPicker({
  catalogue, current, onChoose, onAddKey, onRefresh, variant = "chip", label: triggerLabel,
  disabled = false, open: openProp, onOpenChange, triggerGlyph,
}: ModelPickerProps) {
  const [openState, setOpenState] = useState(false);
  const open = openProp ?? openState;
  const setOpen = useCallback((next: boolean) => {
    if (openProp === undefined) setOpenState(next);
    onOpenChange?.(next);
  }, [openProp, onOpenChange]);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");
  //: Groups the user has explicitly opened or closed. A search opens everything that matches, so a
  //: collapsed group cannot hide a result the user just asked for.
  const [toggled, setToggled] = useState<Record<string, boolean>>({});
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const input = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLDivElement>(null);
  const baseId = useId().replace(/:/g, "");

  const specs = catalogue?.available ?? [];
  const currentSpec = specs.find((s) => s.id === current) ?? null;
  const groups = useMemo(
    () => groupModels(specs, { current, query, collapsedGroups: [GROUP_UNAVAILABLE] })
      .map((g) => (g.name in toggled ? { ...g, collapsed: !toggled[g.name] } : g)),
    [specs, current, query, toggled],
  );
  const rows = useMemo(
    () => groups.filter((g) => !g.collapsed).flatMap((g) => g.rows),
    [groups],
  );
  const notice = catalogue ? sourceNotice(catalogue.source) : "";
  const stale = catalogue ? freshness(catalogue.updatedAt, Date.now()) : "";

  /* The popover is **ported to the body**, not positioned inside the bar.
     Two measured reasons:
       1. `.topbar .meta` has `overflow: hidden` (it may compress, see styles.css) — a child popover
          was clipped to a 32px band and rendered at `y: -332px`, i.e. invisible;
       2. an absolutely-positioned popover inside a `min-width: 0` flex item is still laid out against
          that item, so it reflows the very cluster it hangs from.
     Porting makes the geometry a viewport problem, which is also what lets it flip above the chip
     when there is no room below. */
  const [placement, setPlacement] = useState<{ top: number; left: number; width: number } | null>(null);
  useLayoutEffect(() => {
    if (!open) { setPlacement(null); return; }
    const place = () => {
      const box = trigger.current?.getBoundingClientRect();
      if (!box) return;
      const width = Math.min(POPOVER_WIDTH, window.innerWidth - 24);
      const maxHeight = Math.min(window.innerHeight * 0.6, 520);
      const spaceBelow = window.innerHeight - box.bottom - 12;
      const below = spaceBelow >= Math.min(maxHeight, 320);
      // Above the trigger, the popover may not reach into the top bar (52px): it would be painted over.
      const floor = TOPBAR + 8;
      const top = below ? box.bottom + 6 : Math.max(floor, box.top - 6 - Math.min(maxHeight, box.top - floor));
      const left = Math.min(Math.max(12, box.right - width), window.innerWidth - width - 12);
      setPlacement({ top, left, width });
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open]);

  // The popover opens on the current model, scrolled into view (U9).
  useEffect(() => {
    if (!open) return;
    const at = rows.findIndex((r) => r.spec.id === current);
    setCursor(at >= 0 ? at : rows.findIndex((r) => canChoose(r.spec)));
    const id = window.requestAnimationFrame(() => input.current?.focus());
    return () => window.cancelAnimationFrame(id);
    // `rows` is intentionally not a dependency: re-seating the cursor on every keystroke would fight
    // the keyboard model. It re-seats when the popover opens, which is the documented behaviour.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const el = list.current?.querySelector<HTMLElement>('[data-active="true"]');
    el?.scrollIntoView({ block: "nearest" });
  }, [cursor, open]);

  const close = useCallback((returnFocus = true) => {
    setOpen(false);
    setQuery("");
    // The status is deliberately NOT cleared here: a confirmation ("Switched to X. Applies to your
    // next message.") is set immediately before the popover closes, and clearing it here erased the
    // message the user was supposed to read. `dismiss` is the one that clears it.
    if (returnFocus) trigger.current?.focus();
  }, []);

  const dismiss = useCallback(() => {
    close(true);
    setStatus("");
  }, [close]);

  // Escape closes from anywhere, not only from the search box: focus can be on the trigger, on a row,
  // or nowhere (the palette and ⌘⇧M open the popover without a click), and a popover that ignores
  // Escape in those states cannot be dismissed without hunting for a click target.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented) return;
      e.preventDefault();
      dismiss();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, dismiss]);

  // Outside click closes, the way people expect from a popover.
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      const target = e.target as Node | null;
      // The popover lives in a portal on `document.body`, so "inside" is two checks, not one.
      if (!target) return;
      if (root.current?.contains(target)) return;
      if ((target as HTMLElement).closest?.(".picker")) return;
      close(false);
    };
    window.addEventListener("mousedown", onDown);
    return () => window.removeEventListener("mousedown", onDown);
  }, [open, close]);

  const choose = useCallback(async (spec: ModelSpec, keepOpen = false) => {
    if (!canChoose(spec)) {
      setStatus(availabilityCopy(spec));
      return;
    }
    setBusy(true);
    try {
      await onChoose(spec.id);
      setStatus(`Switched to ${label(spec)}. Applies to your next message.`);
      if (!keepOpen) close(false);
    } catch (err) {
      setStatus(err instanceof Error ? err.message : "the model could not be switched");
    } finally {
      setBusy(false);
    }
  }, [onChoose, close]);

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((p) => (rows.length ? (p + 1) % rows.length : 0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((p) => (rows.length ? (p - 1 + rows.length) % rows.length : 0));
    } else if (e.key === "Home") {
      e.preventDefault();
      setCursor(0);
    } else if (e.key === "End") {
      e.preventDefault();
      setCursor(Math.max(rows.length - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const row = rows[cursor];
      if (row) void choose(row.spec, e.metaKey || e.ctrlKey);
    } else if (e.key === "Escape") {
      e.preventDefault();
      dismiss();
    } else if (e.key === "Tab") {
      close(false);            // a popover must not trap focus: Tab leaves it
    }
  };

  const active = rows[cursor];
  const activeId = active ? `${baseId}-opt-${slug(active.spec.id)}` : undefined;

  return (
    <div className="model-picker" ref={root}>
      <button
        ref={trigger}
        type="button"
        className={variant === "chip" ? "chip model-trigger" : "btn model-trigger"}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-busy={busy}
        aria-label={triggerLabel ?? `Model: ${currentSpec ? label(currentSpec) : current || "none selected"}`}
        title={`Choose the model for this session${currentSpec ? ` — now ${label(currentSpec)}` : ""}`}
        disabled={disabled}
        onClick={() => { if (open) close(false); else { setStatus(""); setOpen(true); } }}
      >
        {(triggerGlyph ?? (variant === "chip" ? "model" : "")) !== "" && (
          <span aria-hidden className="model-trigger-glyph">{triggerGlyph ?? "model"}</span>
        )}
        <span className="model-trigger-label">
          {currentSpec ? label(currentSpec) : current ? current.split("/").slice(1).join("/") : "Choose a model"}
        </span>
        {currentSpec && <StateGlyph spec={currentSpec} />}
        <ChevronDown size={12} />
      </button>

      {open && placement && createPortal(
        <div
          className="picker"
          role="presentation"
          style={{ top: placement.top, left: placement.left, width: placement.width }}
        >
          <div className="picker-head">
            <input
              ref={input}
              className="picker-search"
              role="combobox"
              aria-expanded="true"
              aria-controls={`${baseId}-list`}
              aria-activedescendant={activeId}
              aria-autocomplete="list"
              aria-label="Search models"
              placeholder="Search models…"
              value={query}
              onChange={(e) => { setQuery(e.target.value); setCursor(0); }}
              onKeyDown={onKeyDown}
            />
            <span className="picker-current" title="The model this session is using">
              current: {currentSpec ? label(currentSpec) : "—"}
            </span>
          </div>

          {notice && (
            <p className="picker-notice" role="note">
              <Warning size={13} /> {notice}
            </p>
          )}

          <div className="picker-list" id={`${baseId}-list`} role="listbox" aria-label="Models" ref={list}>
            {specs.length === 0 && (
              <p className="picker-empty">
                No models are available. If this workspace serves models, the AI Gateway is not
                reachable from this app; ask your admin.
              </p>
            )}
            {groups.map((group) => (
              <div key={group.name} className="picker-group" role="group"
                aria-label={`${group.name}, ${group.choosable} of ${group.total} selectable`}>
                <button
                  type="button"
                  className={`picker-group-head${group.matched ? "" : " is-empty"}`}
                  aria-expanded={!group.collapsed && group.matched}
                  aria-label={`${group.name}, ${group.choosable} of ${group.total} selectable${
                    group.matched ? "" : ", no match"}`}
                  disabled={!group.matched}
                  /* Toggling must not steal focus: the keyboard model lives on the search input, and a
                     focus jump to this button made every arrow key after it a no-op. The rows use the
                     same `preventDefault` on mousedown for the same reason. */
                  onMouseDown={(e) => e.preventDefault()}
                  onClick={() => setToggled((t) => ({ ...t, [group.name]: group.collapsed }))}
                >
                  <span className="picker-group-name">
                    {group.matched ? group.name : `${group.name} — no match`}
                  </span>
                  <span className="picker-group-count">
                    {group.matched && group.collapsed && <span className="picker-caret" aria-hidden>▸ </span>}
                    {group.matched ? `${group.choosable} of ${group.total}` : `${group.total} hidden`}
                  </span>
                </button>
                {!group.collapsed && group.rows.map((row) => {
                  const index = rows.findIndex((r) => r.spec.id === row.spec.id);
                  return (
                    <PickerRow
                      key={row.spec.id}
                      id={`${baseId}-opt-${slug(row.spec.id)}`}
                      spec={row.spec}
                      isCurrent={row.spec.id === current}
                      isActive={index === cursor}
                      matchedOn={row.matchedOn}
                      query={query}
                      onHover={() => setCursor(index)}
                      onPick={() => void choose(row.spec)}
                      onAddKey={onAddKey}
                    />
                  );
                })}
              </div>
            ))}
          </div>

          <footer className="picker-foot">
            <span className="picker-keys">
              <kbd>↑</kbd><kbd>↓</kbd> move
              <kbd>⏎</kbd> select
              <kbd>⌘⏎</kbd> keep open
              <kbd>esc</kbd> close
            </span>
            <span className="picker-source">
              {stale}
              {catalogue && ` · source: ${catalogue.source}`}
              {onRefresh && (
                <button className="picker-refresh" onClick={onRefresh} type="button">Refresh</button>
              )}
            </span>
          </footer>
          <p className="picker-summary" aria-live="polite">{searchSummary(groups, query)}</p>
        </div>,
        document.body,
      )}

      {/* A live region, not a toast: a switch is announced, and so is a refusal (E-29). */}
      <span className="sr-only" role="status" aria-live="polite">{status}</span>
      {status && !open && <span className="picker-toast" role="status">{status}</span>}
    </div>
  );
}

function PickerRow({
  id, spec, isCurrent, isActive, matchedOn, query, onHover, onPick, onAddKey,
}: {
  id: string; spec: ModelSpec; isCurrent: boolean; isActive: boolean;
  matchedOn: string; query: string;
  onHover: () => void; onPick: () => void; onAddKey?: (provider: string) => void;
}) {
  const usable = canChoose(spec);
  const copy = availabilityCopy(spec);
  return (
    <div
      id={id}
      role="option"
      aria-selected={isActive}
      aria-disabled={!usable}
      data-active={isActive}
      data-model={spec.id}
      className={`picker-row${isActive ? " is-active" : ""}${usable ? "" : " is-disabled"}`}
      onMouseMove={onHover}
      onMouseDown={(e) => { e.preventDefault(); if (usable) onPick(); }}
    >
      <span className="picker-glyph" aria-hidden>
        {isCurrent ? <Check size={13} /> : usable ? <SpanGlyph glyph={STATE_COPY[spec.state].glyph} /> : <Ring size={11} />}
      </span>
      <span className="picker-main">
        <span className="picker-name">
          {/* The runs must be INSIDE one inline box: `.picker-name` is a flex row with a gap, so
              emitting a `<mark>` and a `<span>` as siblings put 6px of gap between two halves of one
              word — measured as "gemin i-3.8-flash" in a screenshot. */}
          <span className="picker-name-text">
            {highlight(label(spec), query).map((run, i) => (
              run.hit ? <mark key={i}>{run.text}</mark> : <span key={i}>{run.text}</span>
            ))}
          </span>
          {isCurrent && <span className="picker-badge">current</span>}
        </span>
        <span className={`picker-facts${usable ? "" : " is-reason"}`}>
          {usable ? limitsCopy(spec) : copy}
          {matchedOn === "provider" && <span className="picker-why"> · matched provider</span>}
          {matchedOn === "id" && <span className="picker-why"> · matched id</span>}
        </span>
      </span>
      <span className="picker-tail">
        {needsKey(spec) && onAddKey ? (
          <button
            type="button"
            className="picker-add-key"
            aria-label={`Add a key for ${spec.providerName}`}
            onMouseDown={(e) => e.stopPropagation()}
            onClick={(e) => { e.preventDefault(); onAddKey(spec.provider); }}
          >
            Add a key
          </button>
        ) : (
          <span className="picker-wire" title={`${spec.providerName} · ${spec.wire}`}>{providerTag(spec)}</span>
        )}
      </span>
    </div>
  );
}

function SpanGlyph({ glyph }: { glyph: string }) {
  return <span className="picker-bullet">{glyph}</span>;
}

/** The chip's state glyph: the same vocabulary as the rows, so one legend covers the whole surface. */
export function StateGlyph({ spec }: { spec: ModelSpec }) {
  const { glyph, tone, word } = STATE_COPY[spec.state];
  // In the trigger the glyph must mean "there is something to act on". `available` is the normal
  // case and needs no mark; the muted states ("never probed") would otherwise put a bare "?" beside
  // the model name, which reads as a defect rather than as information. The rows and the inspector
  // still spell every state out (spec 006 MC-7).
  const shows = spec.state !== "available" && tone !== "muted";
  if (!shows) return null;
  return (
    <span className={`state-glyph tone-${tone}`} aria-label={word} title={word}>{glyph}</span>
  );
}

/** `provider/model` -> an id safe for `aria-activedescendant` and `querySelector`. */
function slug(id: string): string {
  return id.replace(/[^\w-]/g, "-");
}

/** The chip the topbar renders. Kept as a named export so the shell does not know the props. */
export function ModelChip(props: ModelPickerProps) {
  return <ModelPicker {...props} variant="chip" />;
}

