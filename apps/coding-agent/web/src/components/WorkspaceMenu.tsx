/** Right-click menu for a workspace object, and the small dialogs its actions need.
 *
 * The items come from `menuFor`, so this file only draws them and reports which one was chosen.
 */
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { api } from "../api/client";
import { menuFor, type MenuItem, type MenuNode } from "../domain/workspaceMenu";

export function WorkspaceMenu({ x, y, node, home, favorite, onPick, onClose }: {
  x: number; y: number; node: MenuNode; home: string; favorite: boolean;
  onPick: (id: string) => void; onClose: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ left: x, top: y });
  const sections = menuFor(node, { home, favorite });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    setPos({
      left: Math.max(8, Math.min(x, window.innerWidth - r.width - 8)),
      top: Math.max(8, Math.min(y, window.innerHeight - r.height - 8)),
    });
    el.querySelector<HTMLButtonElement>(".ctx-item")?.focus();
  }, [x, y]);

  useEffect(() => {
    const down = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) onClose(); };
    const key = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("mousedown", down);
    window.addEventListener("keydown", key);
    return () => { window.removeEventListener("mousedown", down); window.removeEventListener("keydown", key); };
  }, [onClose]);

  return createPortal(
    <div ref={ref} className="ctx" role="menu" aria-label={`Actions for ${node.name}`} style={{ left: pos.left, top: pos.top }}>
      {sections.map((section, i) => (
        <div key={section[0]?.id ?? i}>
          {i > 0 && <hr className="ctx-sep" />}
          {section.map((item) => <Item key={item.id} item={item} onPick={onPick} />)}
        </div>
      ))}
    </div>,
    document.body,
  );
}

function Item({ item, onPick }: { item: MenuItem; onPick: (id: string) => void }) {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);
  const [toLeft, setToLeft] = useState(false);
  const has = !!item.children?.length;

  const show = () => {
    if (!has || !item.enabled) return;
    const r = wrap.current?.getBoundingClientRect();
    setToLeft(!!r && r.right + 200 > window.innerWidth);
    setOpen(true);
  };

  return (
    <div className="ctx-item-wrap" ref={wrap} onMouseEnter={show} onMouseLeave={() => setOpen(false)}>
      <button
        type="button" role="menuitem" className={`ctx-item${item.danger ? " is-danger" : ""}${open ? " is-open" : ""}`}
        aria-disabled={!item.enabled} aria-haspopup={has ? "menu" : undefined} aria-expanded={has ? open : undefined}
        title={item.reason} data-id={item.id}
        onClick={() => { if (!item.enabled) return; if (has) show(); else onPick(item.id); }}
        onKeyDown={(e) => {
          if (e.key === "ArrowRight" && has) { e.preventDefault(); show(); }
          if (e.key === "ArrowLeft" && open) { e.preventDefault(); setOpen(false); }
          const list = (e.currentTarget.closest(".ctx") as HTMLElement | null)
            ?.querySelectorAll<HTMLButtonElement>(":scope > .ctx-item, :scope > div > .ctx-item-wrap > .ctx-item");
          if (!list || (e.key !== "ArrowDown" && e.key !== "ArrowUp")) return;
          const buttons = Array.from(list);
          const at = buttons.indexOf(e.currentTarget);
          if (at < 0) return;
          e.preventDefault();
          buttons[(at + (e.key === "ArrowDown" ? 1 : -1) + buttons.length) % buttons.length]?.focus();
        }}
      >
        <span>{item.label}</span>
        {has && <span className="ctx-caret" aria-hidden>›</span>}
      </button>
      {open && item.children && (
        <div className={`ctx ctx-sub${toLeft ? " is-left" : ""}`} role="menu" aria-label={item.label}>
          {item.children.map((child) => (
            <button key={child.id} type="button" role="menuitem" className="ctx-item"
              onClick={() => onPick(child.id)}>{child.label}</button>
          ))}
        </div>
      )}
    </div>
  );
}

export interface PromptState {
  id: "rename" | "move" | "clone" | "create-notebook" | "create-file" | "create-folder" | "trash" | "share";
  node: MenuNode;
  value?: string;
  language?: string;
}

const TITLE: Record<PromptState["id"], string> = {
  rename: "Rename", move: "Move", clone: "Clone",
  "create-notebook": "Create notebook", "create-file": "Create file", "create-folder": "Create folder",
  trash: "Move to Trash", share: "Share (Permissions)",
};

export function ActionDialog({ prompt, busy, error, link, onChange, onCancel, onConfirm }: {
  prompt: PromptState; busy: boolean; error: string; link: string | null;
  onChange: (next: PromptState) => void; onCancel: () => void; onConfirm: () => void;
}) {
  const field = useRef<HTMLInputElement>(null);
  useEffect(() => { field.current?.focus(); field.current?.select(); }, [prompt.id]);
  const danger = prompt.id === "trash";
  const folder = prompt.node.kind === "directory" || prompt.node.kind === "repo";
  const needsName = prompt.id === "rename" || prompt.id === "clone" || prompt.id.startsWith("create");
  const confirm = danger ? "Move to Trash" : TITLE[prompt.id].replace("Create ", "Create");

  return (
    <div className="scrim" role="dialog" aria-modal="true" aria-labelledby="ws-prompt-title" onMouseDown={onCancel}>
      <form className={`sheet ws-prompt${danger ? " is-danger" : ""}`}
        onMouseDown={(e) => e.stopPropagation()}
        onSubmit={(e) => { e.preventDefault(); if (!busy) onConfirm(); }}>
        <header>
          <h2 id="ws-prompt-title">{TITLE[prompt.id]}</h2>
          <p>{prompt.node.path}</p>
        </header>
        <div className="body">
          {prompt.id === "share" && <ShareList path={prompt.node.path} link={link} />}
          {prompt.id === "trash" && <p>This moves <strong>{prompt.node.name}</strong> to the workspace trash.</p>}
          {prompt.id === "move" && (
            <label className="ws-field">Destination folder
              <input ref={field} value={prompt.value ?? ""} spellCheck={false}
                onChange={(e) => onChange({ ...prompt, value: e.target.value })} />
            </label>
          )}
          {needsName && (
            <label className="ws-field">{prompt.id === "create-file" ? "File name" : "Name"}
              <input ref={field} value={prompt.value ?? ""} spellCheck={false}
                placeholder={prompt.id === "create-file" ? "notes.md" : ""}
                onChange={(e) => onChange({ ...prompt, value: e.target.value })} />
            </label>
          )}
          {prompt.id === "create-notebook" && (
            <label className="ws-field">Language
              <select value={prompt.language ?? "PYTHON"} onChange={(e) => onChange({ ...prompt, language: e.target.value })}>
                {["PYTHON", "SQL", "SCALA", "R"].map((l) => <option key={l} value={l}>{l[0] + l.slice(1).toLowerCase()}</option>)}
              </select>
            </label>
          )}
          {(prompt.id === "move" || prompt.id === "clone") && folder && (
            <p className="ws-hint">A folder is copied object by object. Permissions are not copied, and a Git folder inside stops the copy. The original stays until the copy has succeeded.</p>
          )}
          {error && <p className="ws-error" role="alert">{error}</p>}
        </div>
        <div className="actions">
          {prompt.id === "share" ? (
            <>
              {link && <a className="btn primary" href={link} target="_blank" rel="noopener noreferrer">Open in Databricks</a>}
              <button type="button" className="btn ghost" onClick={onCancel}>Close</button>
            </>
          ) : (
            <>
              <button type="button" className="btn ghost" onClick={onCancel} disabled={busy}>Cancel</button>
              <button type="submit" className={danger ? "btn stop" : "btn primary"} disabled={busy}>{busy ? "Working…" : confirm}</button>
            </>
          )}
        </div>
      </form>
    </div>
  );
}

function ShareList({ path, link }: { path: string; link: string | null }) {
  const [rows, setRows] = useState<{ who: string; permission: string; inherited: boolean }[] | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    let live = true;
    api.permissions(path).then(
      (d) => { if (live) setRows(d.entries); },
      (e) => { if (live) setErr(e instanceof Error ? e.message : "could not read permissions"); },
    );
    return () => { live = false };
  }, [path]);
  if (err) return <p className="ws-error" role="alert">{err}</p>;
  if (!rows) return <p className="ws-hint">Reading who has access…</p>;
  if (!rows.length) return <p className="ws-hint">No access entries were returned. Change sharing in Databricks.</p>;
  return (
    <ul className="perm-list">
      {rows.map((r, i) => (
        <li key={`${r.who}-${r.permission}-${i}`}>
          <span className="perm-who">{r.who}</span>
          <span className="perm-level">{r.permission.replaceAll("_", " ").toLowerCase()}{r.inherited ? " · inherited" : ""}</span>
        </li>
      ))}
      {!link && <li className="ws-hint">Open the object in Databricks to change who has access.</li>}
    </ul>
  );
}
