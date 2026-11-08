/** The one model trigger. Two placements, one component (spec 006 MC-2).
 *
 * Why a wrapper at all: the palette's "change the model" command used to find the control with
 * `document.querySelector(".topbar .model-trigger")`, which is a second, implicit knowledge of where
 * the picker lives. With the picker in two places that trick silently stops working. This component
 * owns a `ref` to the trigger and exposes one way to open it, so neither placement is special.
 */
import { useEffect, useRef, useState } from "react";
import { firstVisible } from "../domain/visible";
import { ModelPicker } from "./ModelPicker";
import { label, needsKey, type CatalogueResponse } from "../domain/models";

export interface ModelControlProps {
  catalogue: CatalogueResponse | null;
  current: string;
  onChoose: (id: string) => Promise<void>;
  onAddKey?: (provider: string) => void;
  onRefresh?: () => void;
  /** `chip` in the top bar, `inline` in a composer's action row. */
  variant?: "chip" | "inline";
  disabled?: boolean;
  /** Lets the App open the picker from a shortcut or the palette, wherever it is rendered. */
  openRequest?: number;
}

/** The short label for a narrow control: the model's own name, never a provider path (MC-7). */
export function shortModelLabel(id: string, catalogue: CatalogueResponse | null): string {
  const spec = (catalogue?.available ?? []).find((s) => s.id === id);
  if (spec) return label(spec);
  const tail = id.split("/").pop() ?? id;
  return tail.replace(/^gemini-/, "gemini ");
}

export function ModelControl({
  catalogue, current, onChoose, onAddKey, onRefresh, variant = "chip", disabled, openRequest = 0,
}: ModelControlProps) {
  // An external "open" request (⌘⇧M, the palette) bumps a counter that the app owns. The picker is
  // controlled by `open`, so a click and a shortcut cannot cancel each other: opening is the union of
  // "the user clicked" and "the app asked", and closing clears both.
  const [clicked, setClicked] = useState(false);
  const asked = useRef(openRequest);
  const [asking, setAsking] = useState(false);
  const wrap = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (openRequest === asked.current) return;
    asked.current = openRequest;
    /* The picker is mounted in more than one place (top bar, composer), and every mounted control sees
       the same request. Only the first one that is actually on screen answers: otherwise ⌘⇧M opened
       two popovers at once, one of them mid-screen, and Escape could close neither. A control that is
       display:none (the chip below 1100 px) is skipped, so the shortcut still works at every width. */
    const mine = wrap.current?.querySelector<HTMLElement>(".model-trigger");
    const answers = firstVisible(document.querySelectorAll<HTMLElement>(".model-trigger"));
    if (mine && answers === mine) setAsking(true);
  }, [openRequest]);
  const open = clicked || asking;
  const setOpen = (v: boolean) => { setClicked(v); if (!v) setAsking(false); };

  const spec = (catalogue?.available ?? []).find((s) => s.id === current);
  const short = shortModelLabel(current, catalogue);
  const missingKey = spec ? needsKey(spec) : false;

  return (
    <span ref={wrap} className="model-control">
      <ModelPicker
        catalogue={catalogue}
        current={current}
        onChoose={onChoose}
        onAddKey={onAddKey}
        onRefresh={onRefresh}
        variant={variant === "inline" ? "button" : "chip"}
        triggerGlyph={variant === "inline" ? "model" : undefined}
        label={variant === "inline" ? `Model for this conversation: ${short}` : undefined}
        disabled={disabled}
        open={open}
        onOpenChange={setOpen}
      />
      {variant === "inline" && missingKey && (
        <span className="sr-only">the current model needs a key; open the model list for the remedy</span>
      )}
    </span>
  );
}
