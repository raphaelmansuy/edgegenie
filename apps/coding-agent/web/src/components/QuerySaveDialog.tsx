import { useEffect, useRef, useState } from "react";

/** Native dialog supplies modal focus containment, Escape and focus restoration. */
export function QuerySaveDialog({name,folder,copy,pending,busy,error,onClose,onSave}: {
  name:string;folder:string;copy:boolean;pending:boolean;busy:boolean;error:string;onClose:()=>void;
  onSave:(name:string,parent:string)=>void;
}) {
  const dialog=useRef<HTMLDialogElement>(null);
  const [title,setTitle]=useState(name),[parent,setParent]=useState(folder);
  useEffect(()=>{const node=dialog.current;node?.showModal();return()=>node?.close();},[]);
  return <dialog ref={dialog} className="sql-save-dialog" aria-labelledby="sql-save-title" onCancel={event=>{if(busy)event.preventDefault();else onClose();}}>
    <form onSubmit={event=>{event.preventDefault();onSave(title,parent);}}>
      <span className="sql-eyebrow">SAVE YOUR WORK</span><h2 id="sql-save-title">{copy?"Save a Query copy":"Create SQL Query"}</h2>
      <p>This creates a new Databricks Query. It does not update the original or copy its permissions.</p>
      <label>Query name<input autoFocus aria-label="Saved Query name" value={title} maxLength={200} required onChange={e=>setTitle(e.target.value)} disabled={busy||pending}/></label>
      <label>Workspace folder<input aria-label="Query destination folder" value={parent} maxLength={512} required onChange={e=>setParent(e.target.value)} disabled={busy||pending}/></label>
      <p className="sql-save-note">SQL and execution context are saved. Run parameter values stay private to each execution.</p>
      {error&&<p className="sql-callout is-error" role="alert">{error}</p>}
      <footer><button type="button" className="btn" disabled={busy} onClick={onClose}>Cancel</button><button className="btn primary" type="submit" disabled={busy||!title.trim()||!parent.trim()}>{busy?"Checking…":pending?"Check again":"Create Query"}</button></footer>
    </form>
  </dialog>;
}
