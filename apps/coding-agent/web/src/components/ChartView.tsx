/** A result table as a chart: bar, line, area, scatter or pie, drawn as SVG (see `domain/chart`).
 *  The choice (kind, x, y, group) is the caller's; this draws it and offers to change it. */
import { useMemo } from "react";
import { CHART_KINDS, canChart, columnKinds, describe, model, scene, type ChartKind, type ChartSpec, type ChartTable } from "../domain/chart";

const COLORS = 8;

export function ChartView({ table, spec, onSpec }: { table: ChartTable; spec: ChartSpec; onSpec: (s: ChartSpec) => void }) {
  const m = useMemo(() => model(table, spec), [table, spec]);
  const s = useMemo(() => scene(m), [m]);
  const kinds = useMemo(() => columnKinds(table), [table]);
  const numeric = table.columns.map((c, i) => ({ c, i })).filter(({ i }) => kinds[i] === "number");
  const pie = spec.kind === "pie";

  return (
    <div className="chart">
      <div className="chart-tools" role="group" aria-label="Chart settings">
        <label>Type
          <select value={spec.kind} onChange={(e) => onSpec({ ...spec, kind: e.target.value as ChartKind })}>
            {CHART_KINDS.map((k) => <option key={k.kind} value={k.kind}>{k.label}</option>)}
          </select>
        </label>
        <label>{pie ? "Slices" : "X"}
          <select value={spec.x} onChange={(e) => onSpec({ ...spec, x: Number(e.target.value) })}>
            {table.columns.map((c, i) => <option key={i} value={i}>{c}</option>)}
          </select>
        </label>
        <label>{pie ? "Size" : "Y"}
          <select value={spec.y} onChange={(e) => onSpec({ ...spec, y: Number(e.target.value) })}>
            {numeric.map(({ c, i }) => <option key={i} value={i}>{c}</option>)}
          </select>
        </label>
        {!pie && (
          <label>Group
            <select value={spec.group ?? ""} onChange={(e) => onSpec({ ...spec, group: e.target.value === "" ? null : Number(e.target.value) })}>
              <option value="">None</option>
              {table.columns.map((c, i) => (i === spec.x || i === spec.y ? null : <option key={i} value={i}>{c}</option>))}
            </select>
          </label>
        )}
      </div>

      {s.empty ? (
        <p className="cell-output-note" role="status">Nothing could be drawn with these columns. {m.notes[0] ?? ""}</p>
      ) : (
        <svg className="chart-svg" viewBox={`0 0 ${s.width} ${s.height}`} role="img" aria-label={describe(m)} preserveAspectRatio="xMidYMid meet">
          {!pie && s.yTicks.map((t, i) => (
            <g key={`y${i}`}>
              <line className="chart-grid" x1={s.plot.x} x2={s.plot.x + s.plot.w} y1={t.at} y2={t.at} />
              <text className="chart-tick" x={s.plot.x - 6} y={t.at} textAnchor="end" dominantBaseline="middle">{t.label}</text>
            </g>
          ))}
          {!pie && s.xTicks.map((t, i) => (
            <text key={`x${i}`} className="chart-tick" x={t.at} y={s.plot.y + s.plot.h + 16}
              textAnchor={t.at + t.label.length * 3.4 > s.width - 2 ? "end" : "middle"}><title>{t.full}</title>{t.label}</text>
          ))}
          {!pie && <line className="chart-axis" x1={s.plot.x} x2={s.plot.x + s.plot.w} y1={s.plot.y + s.plot.h} y2={s.plot.y + s.plot.h} />}
          {s.marks.map((k, i) => {
            const c = `chart-c${k.series % COLORS}`;
            if (k.t === "rect") return <rect key={i} className={`chart-bar ${c}`} x={k.x} y={k.y} width={k.w} height={k.h}><title>{k.title}</title></rect>;
            if (k.t === "path") return <path key={i} className={k.area ? `chart-area ${c}` : `chart-line ${c}`} d={k.d} />;
            if (k.t === "dot") return <circle key={i} className={`chart-dot ${c}`} cx={k.x} cy={k.y} r={k.r}><title>{k.title}</title></circle>;
            return <path key={i} className={`chart-slice ${c}`} d={k.d}><title>{k.title}</title></path>;
          })}
        </svg>
      )}

      {s.legend.length > 0 && (
        <ul className="chart-legend" aria-label={pie ? "Slices" : "Groups"}>
          {s.legend.map((l) => (
            <li key={l.series}><span className={`chart-key chart-c${l.series % COLORS}`} aria-hidden />{l.name}{l.detail ? <span className="chart-detail"> {l.detail}</span> : null}</li>
          ))}
        </ul>
      )}
      {m.notes.map((n) => <p key={n} className="cell-output-note">{n}</p>)}
    </div>
  );
}

/** Why the Chart button is off, or "" when it is on. */
export const chartReason = (table: ChartTable): string => canChart(table).why;
