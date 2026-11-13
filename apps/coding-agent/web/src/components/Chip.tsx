/** One attachment, in every state it can be in — and the same component in the composer and the transcript.
 *
 * Extracted from `Composer.tsx` when there started being more than one state to draw. The rule that keeps
 * it honest: **the state is readable without colour.** `failed` says the word, `pending` shows progress,
 * `ready` shows nothing extra — because a chip that only differs by tint is a chip a colour-blind user
 * cannot read (spec 009 [AFC-17], WCAG 1.4.1).
 */
import { createElement, memo } from "react";
import { api } from "../api/client";
import type { Attachment } from "../domain/events";
import { FileIcon, Folder, Notebook, Table } from "./Icons";

import { KIND_ICON } from "./AssetIcon";
export { KIND_ICON } from "./AssetIcon";

export interface ChipProps {
  /** The server-side reference once it exists; also what a thumbnail is fetched by. */
  a: Attachment;
  /** `pending` while the bytes are in flight, `failed` when they are not. Absent means ready/attached. */
  state?: "pending" | "ready" | "failed";
  /** True when the active model cannot consume this file — said on the chip, never hidden. */
  unseen?: boolean;
  /** The sentence to show when `state === "failed"`. */
  reason?: string;
  /** A local object URL for an image that has not landed yet, so the chip has a picture immediately. */
  previewUrl?: string;
  /** The document is the open one, so it is sent automatically. */
  auto?: boolean;
  onRemove?: () => void;
  onRetry?: () => void;
  /** Transcript chips are history: no remove, no retry. */
  fixed?: boolean;
}

function icon(kind: string, name = "") {
  // The glyph says what the file IS. A CSV and a screenshot looking identical is the same class of
  // problem as a tool tag that reads "dbx_write_noteb…": the chip cannot be recognised without reading it.
  const ext = (name.split(".").pop() ?? "").toLowerCase();
  if (["csv", "tsv"].includes(ext)) return createElement(Table, { size: 13 });
  if (["md", "markdown"].includes(ext)) return createElement(Notebook, { size: 13 });
  if (["ipynb"].includes(ext)) return createElement(Notebook, { size: 13 });
  if (kind === "folder") return createElement(Folder, { size: 13 });
  return createElement(KIND_ICON[kind] ?? FileIcon, { size: 13 });
}

const isImage = (a: Attachment, mime?: string) =>
  (mime ?? "").startsWith("image/") || /\.(png|jpe?g|gif|webp)$/i.test(a.name);

/** The chip. Memoised on the values that can actually change, so typing in the composer does not re-render it. */
export const Chip = memo(function Chip({ a, state = "ready", reason, previewUrl, auto, unseen, onRemove, onRetry, fixed }: ChipProps) {
  const pending = state === "pending";
  const failed = state === "failed";
  const showThumb = isImage(a, undefined) && !failed;
  const title = failed
    ? `${reason ?? "This file could not be attached."}`
    : `${a.ref}${auto ? "\nOpen in the viewer, so it is sent with your message" : ""}`;

  return (
    <span
      className={`ctx-chip${auto ? " auto" : ""}${pending ? " is-pending" : ""}${failed ? " is-failed" : ""}`}
      title={title}
      data-state={state}
    >
      {showThumb && a.ref.startsWith("blb_") ? (
        // A URL, never a data: URL. Eight megabytes of base64 in the DOM is a leak per turn, and the
        // transcript would carry one per chip (spec 009 [D11], [V5]).
        <img className="ctx-thumb" src={api.blobUrl(a.ref, true)} alt="" width={20} height={20} />
      ) : (
        <span className="chip-icon" aria-hidden>{previewUrl
          ? <img className="ctx-thumb" src={previewUrl} alt="" width={20} height={20} />
          : icon(a.kind, a.name)}</span>
      )}
      <span className="ctx-name">{a.name}</span>
      {auto && <span className="ctx-tag">open</span>}
      {pending && <span className="ctx-state" aria-label="uploading">uploading</span>}
      {!pending && !failed && unseen && (
        <span className="ctx-state is-unseen" title="The model serving this conversation cannot see inside this file">
          not visible to {a.kind === "blob" ? "this model" : "the model"}
        </span>
      )}
      {failed && <span className="ctx-state is-bad">failed</span>}
      {failed && onRetry && !fixed && (
        <button type="button" className="ctx-retry" aria-label={`Retry ${a.name}`} onClick={onRetry}>↻</button>
      )}
      {onRemove && !fixed && (
        <button type="button" aria-label={`Remove ${a.name}`} onClick={onRemove}>×</button>
      )}
    </span>
  );
});
