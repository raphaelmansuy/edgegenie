import { useCallback, useEffect, useRef, useState } from "react";

/** Decisions must see every saved row, even when the first page contains only deleted resources. */
export async function readWorkRows<T>(path: string, allowMissing = false): Promise<T[]> {
  const items: T[] = [], seen = new Set<string>();
  const url = new URL(path, window.location.origin);
  url.searchParams.set("limit", "100");
  while (true) {
    const response = await fetch(url.pathname + url.search);
    if (response.status === 404 && allowMissing && !seen.size) return [];
    if (!response.ok) throw new Error("Could not read all saved resources or runs. Try again before deciding.");
    const page = await response.json();
    items.push(...page.items);
    if (!page.nextCursor) return items;
    if (seen.has(page.nextCursor)) throw new Error("Saved resource paging did not advance. Reload before deciding.");
    seen.add(page.nextCursor);
    url.searchParams.set("cursor", page.nextCursor);
  }
}
interface Operation {
  id: string;
  nativeId?: string;
  asset: { kind: string; id: string };
  state: string;
}
function StopDialog({
  operations,
  onClose,
  onConfirm,
  error,
  busy,
}: {
  operations: Operation[];
  onClose: () => void;
  onConfirm: (ids: string[]) => void;
  error: string;
  busy: boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [selected, setSelected] = useState<string[]>([]);
  useEffect(() => {
    dialog.current?.showModal();
    return () => dialog.current?.close();
  }, []);
  return (
    <dialog
      ref={dialog}
      className="sql-save-dialog work-stop-dialog"
      aria-labelledby="stop-work-heading"
      onCancel={(e) => {
        if (busy) e.preventDefault();
        else onClose();
      }}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onConfirm(selected);
        }}
      >
        <h2 id="stop-work-heading">Stop work and review its runs</h2>
        <p>
          The agent will stop and its automatic follow-ups will be cancelled.
          Choose which native runs to cancel. Runs you keep remain tracked.
        </p>
        {operations.map((operation) => (
          <label key={operation.id}>
            <input
              type="checkbox"
              checked={selected.includes(operation.id)}
              disabled={!operation.nativeId || busy}
              onChange={(e) =>
                setSelected((ids) =>
                  e.target.checked
                    ? [...ids, operation.id]
                    : ids.filter((id) => id !== operation.id),
                )
              }
            />
            <span>
              {operation.asset.kind}: {operation.asset.id}
              <small>
                {" "}
                · {operation.state}
                {!operation.nativeId
                  ? " · Native handle unknown; lookup is required"
                  : ""}
              </small>
            </span>
          </label>
        ))}
        {error && <p role="alert">{error}</p>}
        <footer>
          <button
            type="button"
            className="btn ghost"
            disabled={busy}
            onClick={onClose}
          >
            Keep working
          </button>
          <button className="btn primary" disabled={busy}>
            {busy
              ? "Stopping…"
              : selected.length
                ? "Stop and cancel selected runs"
                : "Stop agent, keep runs"}
          </button>
        </footer>
      </form>
    </dialog>
  );
}
export function useStopWork(
  sid: string | null,
  enabled: boolean | undefined,
  stopTurn: () => Promise<void>,
) {
  const [operations, setOperations] = useState<Operation[] | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const activeSid = useRef(sid);
  activeSid.current = sid;
  useEffect(() => {
    setOperations(null);
    setError("");
  }, [sid]);
  const stop = useCallback(async () => {
    if (!enabled || !sid) {
      await stopTurn();
      return;
    }
    try {
      const rows = await readWorkRows<Operation>(
        `/api/sessions/${sid}/operations?active=true`,
      );
      if (activeSid.current !== sid) return;
      if (rows.length) {
        setOperations(rows);
        return;
      }
      await stopTurn();
    } catch (e) {
      if (activeSid.current !== sid) return;
      setError((e as Error).message);
      setOperations([]);
    }
  }, [sid, enabled, stopTurn]);
  const confirm = async (ids: string[]) => {
    setBusy(true);
    setError("");
    try {
      await stopTurn();
      for (const id of ids) {
        const response = await fetch(
          `/api/sessions/${sid}/operations/${id}/cancel`,
          { method: "POST" },
        );
        if (!response.ok) {
          const body = await response.json();
          throw new Error(
            body.detail?.message ||
              "The agent stopped, but a native cancellation was not confirmed. Review Runs.",
          );
        }
      }
      setOperations(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return {
    stop,
    dialog: operations && (
      <StopDialog
        operations={operations}
        error={error}
        busy={busy}
        onClose={() => setOperations(null)}
        onConfirm={(ids) => void confirm(ids)}
      />
    ),
  };
}
interface Resource {
  id: string;
  asset: { kind: string; id: string };
  state: string;
}
function ArchiveDialog({
  resources,
  onChoose,
}: {
  resources: Resource[];
  onChoose: (archive: boolean) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    dialog.current?.showModal();
    return () => dialog.current?.close();
  }, []);
  return (
    <dialog
      ref={dialog}
      className="sql-save-dialog"
      aria-labelledby="archive-heading"
      onCancel={() => onChoose(false)}
    >
      <h2 id="archive-heading">Resources left by this session</h2>
      <p>
        Archiving saves the history. These resources remain in the workspace.
        Ongoing compute or storage cost is unknown; archiving does not stop
        those charges.
      </p>
      <ul>
        {resources.map((r) => (
          <li key={r.id}>
            <strong>{r.asset.kind}</strong> <code>{r.asset.id}</code> ·{" "}
            {r.state}
          </li>
        ))}
      </ul>
      <p>
        Use Resources to review cleanup before archiving if you want to remove
        them.
      </p>
      <footer>
        <button className="btn ghost" onClick={() => onChoose(false)}>
          Review resources first
        </button>
        <button className="btn primary" onClick={() => onChoose(true)}>
          Archive, keep resources
        </button>
      </footer>
    </dialog>
  );
}
export function useArchiveReview() {
  const [resources, setResources] = useState<Resource[] | null>(null);
  const resolve = useRef<(value: boolean) => void>(() => {});
  const review = async (sid: string) => {
    const rows = await readWorkRows<Resource>(`/api/sessions/${sid}/resources`, true);
    const remaining = rows.filter(
      (r: Resource) => !["deleted"].includes(r.state),
    );
    if (!remaining.length) return true;
    return new Promise<boolean>((done) => {
      resolve.current = done;
      setResources(remaining);
    });
  };
  const choose = (value: boolean) => {
    resolve.current(value);
    setResources(null);
  };
  return {
    review,
    dialog: resources && (
      <ArchiveDialog resources={resources} onChoose={choose} />
    ),
  };
}
