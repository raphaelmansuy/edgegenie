/** The chip state machine: paste, drop or pick a file, get a chip, watch it become ready.
 *
 * Three rules, each of which is a bug when broken:
 *
 *  1. **The chip exists before the network does.** `add` returns synchronously with a `pending` chip, and
 *     the upload runs behind it. Awaiting the upload first leaves the composer visibly frozen for as long
 *     as the round trip takes (spec 009 [P8], [S2]).
 *  2. **No effect uploads anything.** The upload is started by the event handler and reports back through
 *     the same setter. A `useEffect([file])` is how a double upload happens in StrictMode, and it did in
 *     every implementation that tried it.
 *  3. **A refusal is a sentence, not a silence.** Every refused file produces a chip in `failed` state
 *     carrying the reason, so the composer can show it and offer retry ([AFC-6], [AFC-16]).
 */
import { useCallback, useRef, useState } from "react";
import { api } from "../api/client";
import { MAX_ATTACHMENTS, humanSize, pastedName, refuse, say, type RefusalCode } from "../domain/blob";

export type ChipState = "pending" | "ready" | "failed";

export interface Chip {
  /** Stable across a retry, so a re-render cannot lose the row the user is looking at. */
  key: string;
  name: string;
  /** The local file, kept so a retry re-sends the same bytes without asking the user to paste again. */
  file: File;
  state: ChipState;
  /** Set once the server has accepted it. */
  blobId?: string;
  mime?: string;
  bytes?: number;
  /** Why it failed, in the user's words. */
  reason?: string;
  code?: RefusalCode;
}

export interface BlobUpload {
  chips: Chip[];
  /** Anything the user must be told, cleared as soon as the situation changes. */
  notice: string;
  /** True while any chip is still uploading — the composer disables Send on it. */
  busy: boolean;
  add: (files: FileList | File[], opts: { count: number; modelSeesImages: boolean; model?: string }) => void;
  retry: (key: string, opts: { count: number; modelSeesImages: boolean; model?: string }) => void;
  remove: (key: string) => void;
  clear: () => void;
  setNotice: (s: string) => void;
}

const b64 = (buf: ArrayBuffer): string => {
  const bytes = new Uint8Array(buf);
  let bin = "";
  // Chunked, because `String.fromCharCode(...bytes)` on an 8 MB array overflows the argument list.
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin);
};

export function useBlobUpload(sessionId: string | null, onUploaded?: (c: Chip) => void): BlobUpload {
  const [chips, setChips] = useState<Chip[]>([]);
  const [notice, setNotice] = useState("");
  const seq = useRef(0);

  const patch = useCallback((key: string, next: Partial<Chip>) => {
    setChips((cur) => cur.map((c) => (c.key === key ? { ...c, ...next } : c)));
  }, []);

  /** Send the bytes. Never called before the chip exists, so the UI cannot wait on it. */
  const upload = useCallback(async (chip: Chip) => {
    if (!sessionId) {
      patch(chip.key, { state: "failed", code: "upload_failed",
        reason: say("upload_failed", { name: chip.name, reason: "no session is open" }) });
      return;
    }
    try {
      const content = b64(await chip.file.arrayBuffer());
      const row = await api.uploadBlob(sessionId, chip.name, chip.file.type, content);
      patch(chip.key, { state: "ready", blobId: row.blobId, mime: row.mime, bytes: row.bytes, reason: undefined, code: undefined });
      onUploaded?.({ ...chip, state: "ready", blobId: row.blobId, mime: row.mime, bytes: row.bytes });
    } catch (e) {
      const message = e instanceof Error ? e.message : "the upload failed";
      // A server refusal already carries the finished sentence; a transport failure needs to be phrased.
      const reason = /^[A-Z].*\.$/.test(message)
        ? message
        : say("upload_failed", { name: chip.name, reason: message });
      patch(chip.key, { state: "failed", reason });
    }
  }, [sessionId, patch, onUploaded]);

  const add = useCallback((files: FileList | File[], opts: {
    count: number; modelSeesImages: boolean; model?: string;
  }) => {
    const list = Array.from(files);
    if (list.length === 0) return;
    setNotice("");
    const made: Chip[] = [];
    let refused: { code: RefusalCode; message: string; name: string } | null = null;
    let count = opts.count;

    for (const file of list) {
      const named = file.name && file.name !== "image.png" ? file : new File([file], pastedName(file.type), { type: file.type });
      const refusal = refuse(named, { count, modelSeesImages: opts.modelSeesImages, model: opts.model });
      if (refusal) {
        // One summary sentence for a batch, not one per file: pasting 40 files must not produce 34 chips.
        refused ??= { ...refusal, name: named.name };
        continue;
      }
      const key = `b${(seq.current += 1)}-${named.name}`;
      made.push({ key, name: named.name, file: named, state: "pending" });
      count += 1;
    }

    if (made.length > 0) setChips((cur) => [...cur, ...made]);
    if (refused) setNotice(refused.message);
    // The uploads start AFTER the chips are in state, in the same tick, so the first paint already has them.
    for (const chip of made) void upload(chip);
  }, [upload]);

  const retry = useCallback((key: string, opts: { count: number; modelSeesImages: boolean; model?: string }) => {
    setChips((cur) => {
      const chip = cur.find((c) => c.key === key);
      if (!chip) return cur;
      const refusal = refuse(chip.file, { count: opts.count, modelSeesImages: opts.modelSeesImages, model: opts.model });
      if (refusal) { setNotice(refusal.message); return cur; }
      return cur.map((c) => (c.key === key ? { ...c, state: "pending", reason: undefined, code: undefined } : c));
    });
    const chip = chips.find((c) => c.key === key);
    if (chip) void upload({ ...chip, state: "pending" });
  }, [chips, upload]);

  const remove = useCallback((key: string) => {
    setChips((cur) => cur.filter((c) => c.key !== key));
  }, []);

  const clear = useCallback(() => setChips([]), []);

  const busy = chips.some((c) => c.state === "pending");
  return { chips, notice, busy, add, retry, remove, clear, setNotice };
}

/** What the drop target says it takes, and the one place the limit appears in prose. */
export const DROP_COPY = `Drop to attach — images, text, CSV, notebooks · up to ${humanSize(8 * 1024 * 1024)} each · ${MAX_ATTACHMENTS} per message`;
