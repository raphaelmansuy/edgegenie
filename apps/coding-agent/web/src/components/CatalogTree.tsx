/** Unity Catalog tree: catalogs, schemas, tables. Opens a table viewer; "@" attaches it. */
import { useContext, useEffect, useRef, useState } from "react";
import { api, type CatalogItem } from "../api/client";
import type { Attachment } from "../domain/events";
import { workspaceUrl } from "../domain/links";
import { WorkspaceLinks } from "./DocContext";
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
      {err && <div className="tree-error" style={{ paddingLeft: 30 + depth * 14 }} role="alert">{err}</div>}
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
  const first = useRef(-1);

  useEffect(() => {
    if (first.current === manual) return;
    first.current = manual;
    api.catalog().then((r) => { setRoots(r.items); setError(""); })
      .catch((e) => setError(e instanceof Error ? e.message : "cannot read the catalog"));
  }, [manual]);

  return (
    <div className="tree">
      <div className="tree-search">
        <div className="tree-hint">Unity Catalog, as you can see it</div>
        <button className="btn ghost sm" title="Refresh" aria-label="Refresh catalog" onClick={() => { setRoots(null); setManual((n) => n + 1); }}>⟳</button>
      </div>
      {error && <div className="tree-error" role="alert">{error}</div>}
      {!roots && !error && <div className="tree-empty"><span className="spin" /> loading…</div>}
      <div role="tree" aria-label="Unity Catalog" className="tree-body">
        {roots?.map((c) => <Row key={`${c.ref}:${manual}`} item={c} depth={0} selected={selected}
          onOpenTable={onOpenTable} onAttach={onAttach} />)}
      </div>
      <p className="tree-note">Only catalogs, schemas and tables your account may see are listed.</p>
    </div>
  );
}
