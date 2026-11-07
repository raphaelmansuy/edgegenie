/** The tab strip: it manages its own overflow, so the tab you are looking at is never off screen.
 *
 * A plain `overflow-x: auto` strip loses the active tab the moment there are more tabs than width.
 * Every change to the active tab or the tab list therefore ends with the active tab fully inside the
 * strip, and when tabs are hidden the count is stated (specs/001-perfect-shell SH-C1..C4).
 */
import { useEffect, useRef, useState } from "react";
import { Chat, CloseIcon, Notebook, Table } from "./Icons";
import { tabKeys } from "./Tree";

export interface DocTab {
  id: string;
  name: string;
  kind: string;
  ref: string;
}

const domId = (id: string) => `tab-${id.replace(/[^\w-]/g, "_")}`;

export function DocTabs({ chatId, docs, active, onSelect, onClose }: {
  chatId: string;
  docs: DocTab[];
  active: string;
  onSelect: (id: string) => void;
  onClose: (id: string) => void;
}) {
  const strip = useRef<HTMLDivElement>(null);
  const [hidden, setHidden] = useState(0);

  // After any change, the active tab must be fully visible. "nearest" scrolls the minimum amount, so
  // a tab already in view does not move the strip under the reader's cursor.
  useEffect(() => {
    const el = document.getElementById(domId(active));
    if (!el || !strip.current) return;
    const frame = window.requestAnimationFrame(() => {
      el.scrollIntoView({ block: "nearest", inline: "nearest" });
      // A single scrollIntoView is not enough when the strip grew in the same frame: it scrolls
      // against the old width. Correct with an explicit delta, then re-read. Bounded to 3 passes.
      const s0 = strip.current;
      if (s0) {
        for (let pass = 0; pass < 3; pass += 1) {
          const box = s0.getBoundingClientRect();
          const item = el.getBoundingClientRect();
          const over = item.right - (box.right - 4);
          const under = (box.left + 4) - item.left;
          if (over <= 0 && under <= 0) break;
          s0.scrollLeft += over > 0 ? over : -under;
        }
      }
      const s = strip.current;
      if (!s) return;
      const tabs = Array.from(s.querySelectorAll<HTMLElement>("[data-tab]"));
      const left = s.getBoundingClientRect().left;
      const right = s.getBoundingClientRect().right;
      setHidden(tabs.filter((t) => {
        const r = t.getBoundingClientRect();
        return r.right > right + 1 || r.left < left - 1;
      }).length);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [active, docs.length]);

  if (docs.length === 0) return null;
  const ids = [chatId, ...docs.map((d) => d.id)];

  return (
    <div className="doc-tabs-wrap">
      <div className="doc-tabs" role="tablist" aria-label="Open items" ref={strip}
        onKeyDown={tabKeys(ids, active, onSelect)}>
        <div id={domId(chatId)} data-tab className="doc-tab" role="tab" aria-selected={active === chatId}
          aria-controls="doc-panel" tabIndex={active === chatId ? 0 : -1} onClick={() => onSelect(chatId)}
          onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(chatId); } }}>
          <span className="doc-tab-label">
            <span className="tab-icon" aria-hidden><Chat size={13} /></span> Chat
          </span>
        </div>
        {docs.map((d) => (
          /* The close control lives INSIDE the tab, so it sits within the tab's own shape. One tab
             stop per tab: the strip is one widget, and Delete closes the focused tab. */
          <div key={d.id} id={domId(d.id)} data-tab className="doc-tab" role="tab"
            aria-selected={active === d.id} aria-controls="doc-panel" tabIndex={active === d.id ? 0 : -1}
            onClick={() => onSelect(d.id)} title={d.ref}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSelect(d.id); }
              if (e.key === "Delete" || e.key === "Backspace") { e.preventDefault(); onClose(d.id); }
            }}>
            <span className="doc-tab-label">
              <span className="tab-icon" aria-hidden>
                {d.kind === "table" ? <Table size={13} /> : <Notebook size={13} />}
              </span> {d.name}
            </span>
            <button className="doc-close" tabIndex={-1} aria-label={`Close ${d.name}`}
              title={`Close ${d.name} (⌘W)`}
              onClick={(e) => { e.stopPropagation(); onClose(d.id); }}><CloseIcon /></button>
          </div>
        ))}
      </div>
      {hidden > 0 && (
        <span className="tabs-hidden" title={`${hidden} more tab${hidden === 1 ? "" : "s"} — scroll the strip`}>
          +{hidden}
        </span>
      )}
    </div>
  );
}
