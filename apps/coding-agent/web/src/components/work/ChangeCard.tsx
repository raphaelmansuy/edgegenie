import { useContext, useState } from "react";
import { Context, SessionIdContext, request, type WorkRow } from "./model";
import { Status } from "./Status";
export function ChangeCard({ row }: { row: WorkRow }) {
  const { busy, act } = useContext(Context);
  const [confirmUndo, setConfirmUndo] = useState(false);
  const session = useContext(SessionIdContext);
  const [versions, setVersions] = useState<
    Record<
      string,
      {
        text?: string;
        revision?: string;
        available?: boolean;
        truncated?: boolean;
        operations?: unknown[];
      }
    >
  >();
  const [versionError, setVersionError] = useState("");
  return (
    <article className="work-card" aria-label={`Change ${row.asset.id}`}>
      <header>
        <span>{row.asset.kind} change</span>
        <span role="status">
          <Status state={row.state} />
        </span>
      </header>
      <h3>{row.asset.id.split("/").at(-1) || row.asset.id}</h3>
      <p className="work-path">{row.asset.id}</p>
      <dl className="work-facts">
        <div>
          <dt>Base revision</dt>
          <dd>{row.baseRevision?.slice(0, 12) || "New asset"}</dd>
        </div>
        <div>
          <dt>Fence verdict</dt>
          <dd>
            {(
              row as WorkRow & {
                verdict?: string;
              }
            ).verdict || "Review required"}
          </dd>
        </div>
        <div>
          <dt>Undo</dt>
          <dd>{row.undoAvailable ? "Revision guarded" : "Unavailable"}</dd>
        </div>
      </dl>
      {row.diff && (
        <details open={row.state === "awaiting_review"}>
          <summary>Inspect proposed diff</summary>
          <pre className="work-diff" tabIndex={0}>
            {row.diff}
          </pre>
        </details>
      )}
      {row.reason && <p role="status">{row.reason}</p>}
      {row.state === "conflicted" && (
        <>
          <button
            className="btn ghost"
            onClick={async () => {
              try {
                setVersions(
                  await request(
                    `/api/sessions/${session}/changes/${row.id}/versions`,
                  ),
                );
              } catch (e) {
                setVersionError((e as Error).message);
              }
            }}
          >
            Compare versions
          </button>
          {versionError && <p role="alert">{versionError}</p>}
          {versions &&
            Object.entries(versions).map(([name, value]) => (
              <details key={name} open>
                <summary>
                  {name === "base"
                    ? "Saved base"
                    : name === "proposed"
                      ? "Agent proposal"
                      : "Current workspace version"}
                  {value.revision ? " · " + value.revision.slice(0, 12) : ""}
                </summary>
                {value.available === false ? (
                  <p>
                    The saved base is unavailable. Read the current source and
                    propose again.
                  </p>
                ) : (
                  <pre className="work-diff" tabIndex={0}>
                    {value.text || JSON.stringify(value.operations, null, 2)}
                  </pre>
                )}
                {value.truncated && (
                  <p>
                    Preview capped. Read the full source before proposing again.
                  </p>
                )}
              </details>
            ))}
        </>
      )}

      <div className="work-actions">
        {row.state === "awaiting_review" && (
          <>
            <button
              className="btn primary"
              disabled={busy}
              onClick={() =>
                void act(`changes/${row.id}/decision`, {
                  decision: "apply",
                  key: `${row.id}:apply`,
                })
              }
            >
              Apply change
            </button>
            {row.canRun && (
              <button
                className="btn ghost"
                disabled={busy}
                onClick={() =>
                  void act(`changes/${row.id}/decision`, {
                    decision: "apply_and_run",
                    key: `${row.id}:apply_and_run`,
                  })
                }
              >
                Apply and run
              </button>
            )}
            <button
              className="btn ghost"
              disabled={busy}
              onClick={() =>
                void act(`changes/${row.id}/decision`, {
                  decision: "reject",
                  key: `${row.id}:reject`,
                })
              }
            >
              Reject
            </button>
          </>
        )}
        {row.state === "unknown" && (
          <button
            className="btn ghost"
            disabled={busy}
            onClick={() => void act(`changes/${row.id}/reconcile`)}
          >
            Read to reconcile
          </button>
        )}
        {["applied", "verified"].includes(row.state) &&
          row.undoAvailable &&
          (confirmUndo ? (
            <>
              <span>Restore the saved version?</span>
              <button
                className="btn ghost"
                disabled={busy}
                onClick={() => {
                  void act(`changes/${row.id}/undo`);
                  setConfirmUndo(false);
                }}
              >
                Confirm undo
              </button>
              <button
                className="btn ghost"
                onClick={() => setConfirmUndo(false)}
              >
                Keep change
              </button>
            </>
          ) : (
            <button className="btn ghost" onClick={() => setConfirmUndo(true)}>
              Undo…
            </button>
          ))}
      </div>
    </article>
  );
}
