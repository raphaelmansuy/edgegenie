/** Model facts: the inspector's model block, and the per-turn breakdown that makes FR-10 visible.
 *
 * Below 1100 px the topbar chip is hidden because "the model is in the inspector"
 * (`styles.css`), so this block is not decoration — at a narrow width it is the only place the
 * model is stated. That is why it carries the provider, the wire, the limits with their evidence,
 * the key hint, and **which turn a switch took effect on**.
 */
import { useEffect, useState } from "react";
import { api, type ModelFacts as Facts } from "../api/client";
import { label, limitsCopy, prettyTokens, STATE_COPY, type ModelSpec } from "../domain/models";

export interface ModelFactsProps {
  sessionId: string;
  /** The session's model, so the block states something even before the facts arrive. */
  current: string;
  /** How many turns the session has. A change re-reads the pins: the per-turn breakdown is the
   *  whole point of this block, and it was stale after every turn until this became a dependency. */
  turns?: number;
  onAddKey?: () => void;
}

export function ModelFacts({ sessionId, current, turns = 0, onAddKey }: ModelFactsProps) {
  const [facts, setFacts] = useState<Facts | null>(null);
  const [spec, setSpec] = useState<ModelSpec | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    setError("");
    api.modelFacts(sessionId)
      .then((f) => { if (live) setFacts(f); })
      .catch((err) => { if (live) setError(String(err?.message ?? err)); });
    return () => { live = false; };
  }, [sessionId, current, turns]);

  useEffect(() => {
    if (!current) return;
    let live = true;
    api.model(current).then((s) => { if (live) setSpec(s); }).catch(() => { if (live) setSpec(null); });
    return () => { live = false; };
  }, [current]);

  const counts = countTurns(facts);
  const switchAt = facts?.switchAtTurn ?? null;

  return (
    <div className="fieldset model-facts">
      <legend>Model</legend>
      <p className="model-facts-name">
        <span>{spec ? label(spec) : current || "—"}</span>
        {spec && (
          <span className={`model-facts-state tone-${STATE_COPY[spec.state].tone}`}>
            {STATE_COPY[spec.state].glyph} {STATE_COPY[spec.state].word}
          </span>
        )}
      </p>
      <p className="model-facts-id">{current}</p>

      {spec && (
        <dl className="kv model-facts-dl">
          <dt>Provider</dt><dd>{spec.providerName}</dd>
          <dt>Wire</dt><dd>{spec.wire}</dd>
          <dt>Endpoint</dt><dd className="mono">{spec.endpoint}</dd>
          <dt>Context</dt><dd>{prettyTokens(spec.limits.context)} <Evidence spec={spec} /></dd>
          <dt>Max output</dt><dd>{prettyTokens(spec.limits.output)} <Evidence spec={spec} /></dd>
          <dt>Tools</dt>
          <dd>{spec.capability === "chat_only" ? "no — this model cannot call tools" : "yes"}</dd>
          {spec.credential.kind !== "none" && (
            <>
              <dt>Key</dt>
              <dd>
                {spec.credential.hint || "none yet"}
                {spec.credential.source === "none" && onAddKey && (
                  <> · <button className="link-button" onClick={onAddKey}>add one</button></>
                )}
              </dd>
            </>
          )}
        </dl>
      )}

      {spec?.limits.unverified && (
        <p className="model-facts-warn">
          {limitsCopy(spec)} — the cap is a conservative default, not a measurement.
        </p>
      )}

      {error && <p className="model-facts-warn" role="status">{error}</p>}

      <div className="model-facts-session">
        <p className="model-facts-heading">This session</p>
        <p>
          {facts?.turns.length ?? 0} {facts?.turns.length === 1 ? "turn" : "turns"}
          {counts.length > 0 && ` · ${counts.map(([name, n]) => `${n} on ${name}`).join(" · ")}`}
        </p>
        {switchAt !== null && (
          <p className="model-facts-switch">
            ▲ the switch was at turn {switchAt}. Earlier turns are not retargeted.
          </p>
        )}
        {facts === null && !error && <p className="model-facts-pending">Reading the turn record…</p>}
      </div>
    </div>
  );
}

function Evidence({ spec }: { spec: ModelSpec }) {
  return (
    <span className={`evidence is-${spec.limits.evidence}`} title={`source: ${spec.limits.source}`}>
      {spec.limits.evidence}
    </span>
  );
}

/** Per-model turn counts in the order the models first appear. One definition, used by the line above
 *  and by the tests, so the breakdown cannot disagree with the pins it came from. */
export function countTurns(facts: Facts | null): [string, number][] {
  const order: string[] = [];
  const counts = new Map<string, number>();
  for (const turn of facts?.turns ?? []) {
    const name = turn.model.split("/").slice(1).join("/") || turn.model;
    if (!counts.has(name)) order.push(name);
    counts.set(name, (counts.get(name) ?? 0) + 1);
  }
  return order.map((name) => [name, counts.get(name) ?? 0]);
}
