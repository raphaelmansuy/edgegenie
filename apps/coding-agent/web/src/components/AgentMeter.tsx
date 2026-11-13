/** ACP reports cumulative session cost; never add cumulative updates as turn spend. */
import type { SessionView } from "../domain/events";
export function AgentMeter({ session }: { session: SessionView }) {
  const m = session.meter;
  if (!m) return null;
  const percent = m.size > 0 ? Math.min(100, Math.round(100 * m.used / m.size)) : null;
  return <div className="agent-meter" aria-label="Context and session cost">
    <span title={`${m.used.toLocaleString()} of ${m.size.toLocaleString()} context tokens`}>
      Context {percent === null ? "unknown" : `${percent}%`}</span>
    {percent !== null && <meter min={0} max={100} value={percent} aria-label="Context used" />}
    <span>{m.cost ? `${m.cost.currency} ${m.cost.amount.toFixed(4)} session` : "Cost unknown"}</span>
  </div>;
}
