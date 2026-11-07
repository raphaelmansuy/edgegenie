/** Unity Catalog tree: catalogs, schemas, tables. Opens a table viewer; "@" attaches it. */
import { PaneError } from "./PaneError";
import { useContext, useEffect, useRef, useState } from "react";
import { api, type CatalogItem } from "../api/client";
import type { Attachment } from "../domain/events";
import { workspaceUrl } from "../domain/links";
import { WorkspaceLinks } from "./DocContext";
import { Refresh } from "./Icons";
import { focusFirstChild, focusParent, TreeRow, treeKeys } from "./Tree";

function Row({ item, depth, onOpenTable, onAttach, selected }: {
  item: CatalogItem; depth: number; selected: string | null;
  onOpenTable: (ref: string) => void; onAttach: (a: Attachment) => void;
}) {
  const [open, setOpen] = useState(false);
  const [kids, setKids] = useState<CatalogItem[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const container = item.kind !== "table";
  const [catalog, schema] = item.ref.split(".");
  const tableUrl = workspaceUrl(useContext(WorkspaceLinks), { kind: "table", ref: item.ref });

  const toggle = async () => {
    if (!container) return;
    if (open) { setOpen(false); return; }
    setOpen(true);
    if (kids || loading) return;
    setLoading(true);
    try {
      const r = item.kind === "catalog" ? await api.catalog(item.name) : await api.catalog(catalog, schema);
      setKids(r.items); setErr("");
    } catch (e) { setErr(e instanceof Error ? e.message : "cannot read this"); }
    finally { setLoading(false); }
  };

  return (
    <>
      <TreeRow
        depth={depth} expanded={container ? open : undefined} selected={selected === item.ref} loading={loading}
        caret={container} icon={item.kind} iconClass={`kind-${item.kind}`}
        name={item.name} title={item.comment ? `${item.ref}\n${item.comment}` : item.ref}
        actions={item.kind === "table"
          ? [{ label: `Attach table ${item.name}`, glyph: "@", run: () => onAttach({ kind: "table", ref: item.ref, name: item.ref }) },
             ...(tableUrl ? [{ label: `Open ${item.name} in Databricks`, glyph: "↗", href: tableUrl }] : [])]
          : undefined}
        onActivate={() => (container ? void toggle() : onOpenTable(item.ref))}
        onKeyDown={(e) => {
          if (e.key === "ArrowRight" && container) { e.preventDefault(); if (!open) void toggle(); else focusFirstChild(e.currentTarget); }
          if (e.key === "ArrowLeft") { e.preventDefault(); if (container && open) void toggle(); else focusParent(e.currentTarget); }
          treeKeys(e);
        }}
      />
      {err && <PaneError message={err} indent={30 + depth * 14 - 8} />}
      {open && kids && (
        <div role="group">
          {kids.length === 0 && !err && <div className="tree-empty" style={{ paddingLeft: 30 + depth * 14 }}>(empty)</div>}
          {kids.map((k) => <Row key={k.ref} item={k} depth={depth + 1} selected={selected}
            onOpenTable={onOpenTable} onAttach={onAttach} />)}
        </div>
      )}
    </>
  );
}

export function CatalogTree({ onOpenTable, onAttach, selected }: {
  onOpenTable: (ref: string) => void; onAttach: (a: Attachment) => void; selected: string | null;
}) {
  const [roots, setRoots] = useState<CatalogItem[] | null>(null);
  const [error, setError] = useState("");
  const [manual, setManual] = useState(0);
  /** In flight. Distinct from `!roots`, which is also true after a failure — a refresh button that
   *  spins forever because the request errored is worse than one that never spins. */
  const [loading, setLoading] = useState(true);
  const first = useRef(-1);

  useEffect(() => {
    if (first.current === manual) return;
    first.current = manual;
    setLoading(true);
    api.catalog().then((r) => { setRoots(r.items); setError(""); })
      .catch((e) => setError(e instanceof Error ? e.message : "cannot read the catalog"))
      .finally(() => setLoading(false));
  }, [manual]);

  return (
    <div className="tree">
      <div className="tree-search">
        <div className="tree-hint">Unity Catalog, as you can see it</div>
        {/* A real icon, not the ⟳ character: the glyph was 12px inside a 24x27 button, below the
            24px target and sized by the font rather than the grid. It also spins while the reload
            is in flight, so the control reports its own progress. */}
        <button className="icon-btn tree-refresh" title="Refresh the catalog" aria-label="Refresh the catalog"
          disabled={loading}
          onClick={() => { setRoots(null); setManual((n) => n + 1); }}>
          <Refresh size={15} className={loading ? "spin" : ""} />
        </button>
      </div>
      {error && <PaneError message={error} onRetry={() => { setRoots(null); setError(""); setManual((n) => n + 1); }} />}
      {/* The skeleton is INSIDE the tree box, not above it: as a sibling it occupied 51px that
          vanished when the catalog arrived, which pulled every row upward. Inside, the box keeps
          its geometry and only its children are replaced. */}
      <div role="tree" aria-label="Unity Catalog" className="tree-body">
        {!roots && !error && (
          <div className="sk-list" role="status" aria-label="Loading the catalog">
            {[0, 1, 2].map((i) => (
              <div className="sk-row" key={i}><span className="sk a" /><span className="sk b" /></div>
            ))}
          </div>
        )}
        {roots?.map((c) => <Row key={`${c.ref}:${manual}`} item={c} depth={0} selected={selected}
          onOpenTable={onOpenTable} onAttach={onAttach} />)}
      </div>
      <p className="tree-note">Only catalogs, schemas and tables your account may see are listed.</p>
    </div>
  );
}
