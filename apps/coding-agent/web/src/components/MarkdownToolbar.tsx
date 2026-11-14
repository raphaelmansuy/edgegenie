import { useEffect, useRef, useState } from "react";
import { formatSource, type Format } from "../domain/markdown/format";
import { destination } from "../domain/markdown/policy";
import type { EditorHost } from "../editor/host";

const TOOLS: [Format, string, string][] = [["bold","B","Bold"],["italic","I","Italic"],["code","<>","Inline code"],["link","Link","Insert link"],["image","Image","Insert image reference"],["h1","H1","Heading 1"],["h2","H2","Heading 2"],["h3","H3","Heading 3"],["list","List","Bulleted list"],["quote","Quote","Blockquote"]];
export function MarkdownToolbar({ host, disabled, documentPath }: { host: { current: EditorHost | null }; disabled: boolean; documentPath: string }) {
  const [dialog, setDialog] = useState<{ command: "link" | "image"; start: number; end: number; source: string } | null>(null);
  const [label, setLabel] = useState(""); const [url, setUrl] = useState(""); const [notice, setNotice] = useState("");
  const dialogRef = useRef<HTMLDialogElement>(null);
  useEffect(() => { if (dialog) { dialogRef.current?.showModal?.(); dialogRef.current?.querySelector<HTMLInputElement>("input")?.focus(); } }, [dialog]);
  const close = () => { dialogRef.current?.close?.(); setDialog(null); host.current?.focus(); };
  const invoke = (command: Format) => {
    if (disabled || !host.current) return;
    const selection = host.current.getSelection?.();
    if (!selection || selection.multiple) { setNotice("Choose one contiguous selection to format."); return; }
    if (command === "link" || command === "image") {
      setLabel(host.current.getValue().slice(selection.start, selection.end)); setUrl(""); setNotice("");
      setDialog({ command, start: selection.start, end: selection.end, source: host.current.getValue() }); return;
    }
    host.current.applyEdit?.(formatSource(host.current.getValue(), selection.start, selection.end, command));
    setNotice("");
  };
  const target = destination(url, documentPath);
  const valid = !!label.trim() && target.kind !== "blocked" && (dialog?.command !== "image" || ["external","workspace","volume"].includes(target.kind));
  return <>
    <div className="markdown-toolbar" role="toolbar" aria-label="Markdown formatting" onKeyDown={e => {
      if (!["ArrowLeft","ArrowRight","Home","End"].includes(e.key)) return;
      const buttons = Array.from(e.currentTarget.querySelectorAll<HTMLButtonElement>("button:not(:disabled)"));
      const i = buttons.indexOf(e.target as HTMLButtonElement); if (i < 0) return;
      e.preventDefault(); const at = e.key === "Home" ? 0 : e.key === "End" ? buttons.length - 1 : (i + (e.key === "ArrowRight" ? 1 : -1) + buttons.length) % buttons.length;
      buttons.forEach((b, n) => { b.tabIndex = n === at ? 0 : -1; }); buttons[at]?.focus();
    }}>
      {TOOLS.map(([command, text, name], i) => <button type="button" key={command} aria-label={name} title={name} tabIndex={i === 0 ? 0 : -1} disabled={disabled}
        onMouseDown={e => e.preventDefault()} onClick={() => invoke(command)}>{text}</button>)}
    </div>
    {notice && <p className="markdown-toolbar-notice" role="status">{notice}</p>}
    {dialog && <dialog ref={dialogRef} className="markdown-reference-dialog" aria-label={dialog.command === "image" ? "Insert image reference" : "Insert link"}
      onCancel={e => { e.preventDefault(); e.stopPropagation(); close(); }} onKeyDown={e => e.stopPropagation()}>
      <form onSubmit={e => { e.preventDefault(); if (!valid || disabled || !host.current) return;
        if (host.current.getValue() !== dialog.source) { setNotice("The cell changed. Close this dialog and select the text again."); return; }
        host.current.applyEdit?.(formatSource(dialog.source, dialog.start, dialog.end, dialog.command, { label, url })); close(); }}>
        <h3>{dialog.command === "image" ? "Insert image reference" : "Insert link"}</h3>
        <label>{dialog.command === "image" ? "Image description" : "Link text"}<input value={label} onChange={e => setLabel(e.target.value)} required /></label>
        <label>Destination<input value={url} onChange={e => setUrl(e.target.value)} placeholder="https://… or ./workspace-file" required /></label>
        {url && !valid && <p role="status">{target.reason || "Enter a description and a supported destination."}</p>}
        {dialog.command === "image" && <p>Inserts a reference. The image loads only when you choose Load image.</p>}
        <div><button type="button" className="btn" onClick={close}>Cancel</button><button className="btn primary" disabled={!valid || disabled}>Insert</button></div>
      </form>
    </dialog>}
  </>;
}
