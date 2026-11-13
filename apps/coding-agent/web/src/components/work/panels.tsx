import { useContext, useEffect, useRef, useState } from "react";
import { Context, SessionIdContext, request, type WorkRow } from "./model";
import { Status } from "./Status";
import { ChangeCard } from "./ChangeCard";
import { OperationResult } from "./OperationResult";
import { AssetBrowser } from "./AssetBrowser";
export const WORK_TABS = [
  "changes",
  "runs",
  "assets",
  "capabilities",
  "resources",
  "budget",
] as const;
export type WorkTab = (typeof WORK_TABS)[number];
export function WorkPanel({ tab }: { tab: WorkTab }) {
  const { data, error, busy, act, reload, setReviewing } = useContext(Context);
  useEffect(() => {
    setReviewing(tab === "changes");
    return () => setReviewing(false);
  }, [tab, setReviewing]);
  const [limit, setLimit] = useState("");
  const [unit, setUnit] = useState("tokens");
  const session = useContext(SessionIdContext);
  const ledgerKind = (
    { changes: "change", runs: "operation", resources: "resource" } as Record<
      string,
      string
    >
  )[tab];
  const [ledgerPage, setLedgerPage] = useState<{
    items: WorkRow[];
    nextCursor: string;
  }>();
  const [cursorStack, setCursorStack] = useState<string[]>([""]);
  const [pageError, setPageError] = useState("");
  const pageGeneration = useRef(0);
  useEffect(() => {
    pageGeneration.current++;
    setPageError("");
    setLedgerPage(undefined);
    setCursorStack([""]);
    return () => { pageGeneration.current++; };
  }, [tab, session]);
  async function pageLedger(cursor: string, back = false) {
    const generation = ++pageGeneration.current;
    setPageError("");
    try {
      const path =
        ledgerKind === "change"
          ? "changes"
          : ledgerKind === "operation"
            ? "operations"
            : "resources";
      const page = await request(
        `/api/sessions/${session}/${path}?cursor=${encodeURIComponent(cursor)}`,
      );
      if (generation !== pageGeneration.current) return;
      setLedgerPage(page);
      setCursorStack((stack) =>
        back ? stack.slice(0, -1) : [...stack, cursor],
      );
    } catch (e) {
      if (generation === pageGeneration.current) setPageError((e as Error).message);
    }
  }
  if (!data) return <p role="status">{error || "Loading saved work…"}</p>;
  return (
    <section className="work-panel" aria-label={tab}>
      <header className="work-heading">
        <div>
          <h3>{tab[0].toUpperCase() + tab.slice(1)}</h3>
          <p>
            {
              {
                changes:
                  "Review exact changes before they reach your workspace.",
                runs: "Saved native handles keep runs observable across reconnects.",
                assets: "Find assets using your current workspace permissions.",
                capabilities:
                  "Available actions are checked as your signed-in identity.",
                resources:
                  "Resources created by this session. Cleanup always needs review.",
                budget: "Set a session limit before the next agent pass.",
              }[tab]
            }
          </p>
        </div>
        <button
          className="btn ghost"
          disabled={busy}
          onClick={() => {
            pageGeneration.current++;
            setPageError("");
            setLedgerPage(undefined);
            setCursorStack([""]);
            void reload();
          }}
        >
          Refresh
        </button>
      </header>
      {(error || pageError) && (
        <p role="alert" className="work-error">
          {error || pageError}
        </p>
      )}
      {tab === "changes" &&
        ((ledgerPage?.items ?? data.change).length ? (
          (ledgerPage?.items ?? data.change).map((r) => (
            <ChangeCard row={r} key={r.id} />
          ))
        ) : (
          <p className="work-empty">
            No changes proposed. Ask the agent to inspect an asset and propose a
            focused edit.
          </p>
        ))}
      {tab === "runs" &&
        ((ledgerPage?.items ?? data.operation).length ? (
          (ledgerPage?.items ?? data.operation).map((r) => (
            <article className="work-card" key={r.id}>
              <header>
                {r.asset.kind}
                <Status state={r.state} />
              </header>
              <h3>{r.asset.id}</h3>
              <dl className="work-facts">
                <div>
                  <dt>Native handle</dt>
                  <dd>{r.nativeId || "Awaiting confirmation"}</dd>
                </div>
                <div>
                  <dt>Execution tier</dt>
                  <dd>{r.tier || "Unknown"}</dd>
                </div>
                <div>
                  <dt>Run identity</dt>
                  <dd>{r.ranAs || "Unknown"}</dd>
                </div>
                <div>
                  <dt>Last observed</dt>
                  <dd>
                    {r.lastObservedAt ? (
                      <time
                        dateTime={new Date(
                          r.lastObservedAt * 1000,
                        ).toISOString()}
                      >
                        {new Date(r.lastObservedAt * 1000).toLocaleString()}
                      </time>
                    ) : (
                      "Awaiting observation"
                    )}
                  </dd>
                </div>
              </dl>
              {r.reason && <p>{r.reason}</p>}
              {r.undoAvailable === false && <p>This operation has no undo.</p>}
              {r.result !== undefined && (
                <details>
                  <summary>Observed result</summary>
                  <OperationResult row={r} />
                </details>
              )}
              <div className="work-actions">
                <label>
                  When settled{" "}
                  <select
                    aria-label={`Wake-up for ${r.id}`}
                    value={r.wakeup || "notify"}
                    disabled={busy}
                    onChange={(e) =>
                      void act(`operations/${r.id}/wakeup`, {
                        action: e.target.value,
                      })
                    }
                  >
                    <option value="notify">Notify me</option>
                    <option value="continue">Continue once</option>
                    <option value="none">No follow-up</option>
                  </select>
                </label>
                {["running", "unobserved", "cancelling"].includes(r.state) && (
                  <button
                    className="btn ghost"
                    disabled={busy || r.state === "cancelling"}
                    onClick={() => void act(`operations/${r.id}/cancel`)}
                  >
                    Cancel run
                  </button>
                )}
              </div>
            </article>
          ))
        ) : (
          <p className="work-empty">
            No runs yet. A submitted run appears here with its saved native
            handle.
          </p>
        ))}
      {tab === "capabilities" && (
        <>
          <button
            className="btn ghost"
            disabled={busy}
            onClick={() => void act("capabilities/recheck")}
          >
            Re-check permissions
          </button>
          <div className="work-table-wrap">
            <table className="work-table">
              <thead>
                <tr>
                  <th>Asset</th>
                  <th>Tier</th>
                  <th>Read</th>
                  <th>Change</th>
                  <th>Run</th>
                </tr>
              </thead>
              <tbody>
                {data.capabilities.map((c) => (
                  <tr key={c.kind}>
                    <th scope="row">
                      {c.label}
                      {c.reason && <small>{c.reason}</small>}
                    </th>
                    <td>{c.tier}</td>
                    {[c.read, c.change, c.run].map((v, i) => (
                      <td key={i}>{v ? "Available" : "Unavailable"}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      {tab === "resources" &&
        ((ledgerPage?.items ?? data.resource).length ? (
          (ledgerPage?.items ?? data.resource).map((r) => (
            <article className="work-card" key={r.id}>
              <header>
                {r.asset.kind}
                <Status state={r.state} />
              </header>
              <h3>{r.asset.id}</h3>
              {r.reason && <p>{r.reason}</p>}
              <div className="work-actions">
                {["unknown", "deleting"].includes(r.state) && <button className="btn ghost" disabled={busy} onClick={() => void act(`resources/${r.id}/reconcile`)}>Check cleanup outcome</button>}
                {["present", "absent"].includes(r.state) && <button className="btn ghost" disabled={busy} onClick={() => void act(`resources/${r.id}/acknowledge`, {confirm:true})}>Acknowledge and keep resource</button>}
                {r.state === "present" && (
                  <button
                    className="btn ghost"
                    disabled={busy}
                    onClick={() => void act(`resources/${r.id}/review`)}
                  >
                    Review cleanup
                  </button>
                )}
                {r.state === "cleanup_pending" && (
                  <>
                    <p>
                      Delete this session-created resource? Its revision will be
                      checked again.
                    </p>
                    <button
                      className="btn ghost"
                      disabled={busy}
                      onClick={() =>
                        void act(`resources/${r.id}/cleanup`, { confirm: true })
                      }
                    >
                      Confirm deletion
                    </button>
                    <button
                      className="btn ghost"
                      disabled={busy}
                      onClick={() =>
                        void act(`resources/${r.id}/cleanup`, {
                          confirm: false,
                        })
                      }
                    >
                      Keep resource
                    </button>
                  </>
                )}
              </div>
            </article>
          ))
        ) : (
          <p className="work-empty">
            This session has not created any resources.
          </p>
        ))}
      {tab === "budget" && (
        <div className="work-card">
          <dl className="work-facts">
            <div>
              <dt>Recorded tokens</dt>
              <dd>{data.usedTokens.toLocaleString()}</dd>
            </div>
            <div>
              <dt>Recorded cost</dt>
              <dd>
                {data.currency
                  ? `${data.usedCost.toFixed(4)} ${data.currency}`
                  : "Unknown"}
              </dd>
            </div>
            <div>
              <dt>Current limit</dt>
              <dd>
                {data.budget
                  ? `${data.budget.limit.toLocaleString()} ${data.budget.unit}`
                  : "No session limit"}
              </dd>
            </div>
          </dl>
          <form
            className="work-actions"
            onSubmit={(e) => {
              e.preventDefault();
              void act("budget", { limit: Number(limit), unit });
            }}
          >
            <label>
              Limit{" "}
              <input
                type="number"
                min="1"
                required
                value={limit}
                onChange={(e) => setLimit(e.target.value)}
              />
            </label>
            <label>
              Unit{" "}
              <select value={unit} onChange={(e) => setUnit(e.target.value)}>
                <option value="tokens">Tokens</option>
                <option value="money" disabled={!data.currency}>
                  Money{!data.currency ? " (cost unknown)" : ""}
                </option>
              </select>
            </label>
            <button className="btn primary" disabled={busy}>
              Set budget
            </button>
          </form>
          <p>
            The server checks this limit before another pass or tool dispatch.
            Usage is recorded for every pass, including checks.
          </p>
        </div>
      )}
      {ledgerKind && (
        <nav className="work-actions" aria-label="Ledger pages">
          {cursorStack.length > 1 && (
            <button
              className="btn ghost"
              onClick={() => void pageLedger(cursorStack.at(-2) || "", true)}
            >
              Newer records
            </button>
          )}
          {(ledgerPage?.nextCursor ?? data.cursors?.[ledgerKind]) && (
            <button
              className="btn ghost"
              onClick={() =>
                void pageLedger(
                  ledgerPage?.nextCursor ?? data.cursors?.[ledgerKind] ?? "",
                )
              }
            >
              Older records
            </button>
          )}
        </nav>
      )}
      {tab === "assets" && <AssetBrowser data={data} session={session} />}
    </section>
  );
}
