/** The notebook's widgets: one input each, above the cells. Declared by `dbutils.widgets` in a Python cell, or
 *  implied by a `:name` in a SQL cell (see `domain/widgets`). Changing one does not run anything. */
import { useId } from "react";
import { toggleChoice, valueOf, type BarItem } from "../domain/widgets";

function Field({ item, value, onChange }: { item: BarItem; value: string; onChange: (v: string) => void }) {
  const id = useId();
  const label = (
    <>{item.label}{item.implicit && <em className="widget-hint"> · SQL</em>}</>
  );
  const title = item.implicit ? `Used as :${item.name} in a SQL cell` : item.name;
  if (item.kind === "multiselect") {
    const on = new Set(value.split(",").filter(Boolean));
    return (
      <div className="widget-field" title={title}>
        <span className="widget-label" id={`${id}-l`}>{label}</span>
        <span className="widget-multi" role="group" aria-labelledby={`${id}-l`}>
          {item.choices.map((c) => (
            <label key={c}><input type="checkbox" checked={on.has(c)} onChange={() => onChange(toggleChoice(item, value, c))} />{c}</label>
          ))}
        </span>
      </div>
    );
  }
  return (
    <div className="widget-field" title={title}>
      <label className="widget-label" htmlFor={id}>{label}</label>
      {item.kind === "dropdown" ? (
        <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
          {item.choices.map((c) => <option key={c} value={c}>{c}</option>)}
        </select>
      ) : (
        <>
          <input id={id} type="text" value={value} onChange={(e) => onChange(e.target.value)}
            list={item.kind === "combobox" ? `${id}-o` : undefined} />
          {item.kind === "combobox" && <datalist id={`${id}-o`}>{item.choices.map((c) => <option key={c} value={c} />)}</datalist>}
        </>
      )}
    </div>
  );
}

export function WidgetBar({ items, values, onChange, onReset }: {
  items: BarItem[];
  values: Record<string, string>;
  onChange: (name: string, value: string) => void;
  onReset: () => void;
}) {
  if (items.length === 0) return null;
  const changed = items.some((i) => valueOf(i, values) !== i.default);
  return (
    <section className="widget-bar" aria-label="Notebook widgets">
      <div className="widget-fields">
        {items.map((item) => (
          <Field key={item.name} item={item} value={valueOf(item, values)} onChange={(v) => onChange(item.name, v)} />
        ))}
      </div>
      <span className="widget-note">Changing a widget does not re-run any cell. Run it again to use the new value.</span>
      <button type="button" className="widget-reset" disabled={!changed} onClick={onReset}>Reset</button>
    </section>
  );
}
