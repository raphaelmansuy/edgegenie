import { AgentUpdates } from "../AgentUpdates";
import { useContext } from "react";
import { Context, SessionFeatures } from "./model";
import { ChangeCard } from "./ChangeCard";
import { QuestionCard } from "./QuestionCard";
import { Status } from "./Status";
export function WorkComposerBar() {
  const { data, busy, act, error } = useContext(Context);
  if (!data) return null;
  return (
    <div className="work-composer-bar">
      <label>
        Autonomy{" "}
        <select
          aria-label="Autonomy mode"
          value={data.mode}
          disabled={busy}
          onChange={(e) => void act("mode", { mode: e.target.value })}
        >
          <option value="plan">Plan</option>
          <option value="review">Review</option>
          <option value="auto">Auto</option>
        </select>
      </label>
      <span>{data.toolCount} tools available</span>
      {error && <p role="alert">{error}</p>}
    </div>
  );
}
export function PendingWork() {
  const { data, busy, act, reviewing } = useContext(Context);
  const session = useContext(SessionFeatures);
  const questions = (session.questions ?? []).filter(
    (q) => q.state === "pending" || q.state === "expired",
  );
  const changes = (reviewing ? [] : (data?.change ?? [])).filter(
    (r) => r.state === "awaiting_review",
  );
  const reviews = (data?.approval ?? []).filter(
    (r) => r.state === "pending" && r.action === "run",
  );
  return (
    <div className="work-pending">
      {questions.map((q) => (
        <QuestionCard key={q.id} question={q} />
      ))}
      <AgentUpdates notices={session.notices} compactions={session.compactions} />
      {changes.map((r) => (
        <ChangeCard key={r.id} row={r} />
      ))}
      {reviews.map((r) => (
        <article className="work-card" key={r.id}>
          <header>
            Run requires review
            <Status state={r.state} />
          </header>
          <h3>{r.asset.kind}</h3>
          <p className="work-path">{r.asset.id}</p>
          {r.arguments && (
            <details open>
              <summary>Run inputs</summary>
              <pre className="work-diff" tabIndex={0}>
                {JSON.stringify(r.arguments, null, 2)}
              </pre>
            </details>
          )}
          <div className="work-actions">
            <button
              className="btn primary"
              disabled={busy}
              onClick={() => void act(`run-reviews/${r.id}`, { confirm: true })}
            >
              Run as me
            </button>
            <button
              className="btn ghost"
              disabled={busy}
              onClick={() =>
                void act(`run-reviews/${r.id}`, { confirm: false })
              }
            >
              Reject run
            </button>
          </div>
        </article>
      ))}
    </div>
  );
}
