import { useContext, useEffect, useRef, useState } from "react";
import { queries } from "../api/queries";
import { ApiError } from "../api/client";
import type { Doc } from "../domain/docs";
import type { Attachment } from "../domain/events";
import { ACTIVE_SQL, recoveredSqlInputsChanged, clearQueryCreate, pendingQueryCreate, rememberQueryCreate, clearQueryRecovery, parameterNames, recoverQuery, rememberQuery, type SqlCapabilities, type SqlParameter, type SqlQuery, type SqlRun } from "../domain/query";
import type { EditorHost } from "../editor/host";
import { Editor } from "../editor/Editor";
import { SqlResults } from "./SqlResults";
import { QuerySaveDialog } from "./QuerySaveDialog";
import { workspaceUrl } from "../domain/links";
import { WorkspaceLinks } from "./DocContext";
import { copyText } from "../domain/clipboard";

export function QueryEditor({doc,scope,theme,folder,onDirty,onRename,onSaved,onAttach,onCapture}: {
  onCapture:(capture:(()=>Promise<Attachment>)|null)=>void;
  doc:Doc;scope:string;theme:"light"|"dark";folder:string;onDirty:(doc:Doc,dirty:boolean)=>void;
  onRename:(doc:Doc,name:string)=>void;onSaved:(doc:Doc,query:SqlQuery)=>void;onAttach:(a:Attachment)=>void;
}) {
  const [source,setSource]=useState<SqlQuery|null>(null),[initial,setInitial]=useState("");
  const [name,setName]=useState(doc.name),[warehouse,setWarehouse]=useState(""),[catalog,setCatalog]=useState(""),[schema,setSchema]=useState("");
  const [warehouses,setWarehouses]=useState<{id:string;name:string;state:string}[]>([]),[caps,setCaps]=useState<SqlCapabilities|null>(null);
  const [error,setError]=useState(""),[notice,setNotice]=useState(""),[busy,setBusy]=useState(false),[params,setParams]=useState<SqlParameter[]>([]);
  const [run,setRun]=useState<SqlRun|null>(null),[runError,setRunError]=useState(""),[resultTab,setResultTab]=useState<"results"|"source">("results");
  const [mobileTab,setMobileTab]=useState<"editor"|"results">("editor"),[selection,setSelection]=useState(false),[storageOk,setStorageOk]=useState(true);
  const editor=useRef<EditorHost|null>(null),text=useRef(""),saved=useRef<SqlQuery|null>(null),bufferTimer=useRef<ReturnType<typeof setTimeout>|null>(null);
  const [generation,setGeneration]=useState(0),runInput=useRef("");
  const [saveTarget,setSaveTarget]=useState({name:doc.name,parent:folder});
  const [saveDialog,setSaveDialog]=useState(false),[saveError,setSaveError]=useState(""),[pendingCreate,setPendingCreate]=useState(false);
  const workspace=useContext(WorkspaceLinks);
  const latest=useRef({name,warehouse,catalog,schema});latest.current={name,warehouse,catalog,schema};
  const active=!!run&&ACTIVE_SQL.has(run.state);
  const signature=()=>JSON.stringify([text.current,latest.current.warehouse,latest.current.catalog,latest.current.schema,params]);
  const persist=()=>setStorageOk(rememberQuery(scope,doc.id,text.current,latest.current.name,source?.text));
  useEffect(()=>{
    let live=true;
    void Promise.all([queries.get(doc.kind,doc.ref),queries.warehouses(),queries.capabilities()]).then(([q,w,c])=>{
      if(!live)return;
      const recovery=recoverQuery(scope,doc.id);
      const original=q.text??"";
      const restored=recovery&&recovery.text!==original;
      text.current=restored?recovery.text:original;setInitial(text.current);setSource(q);
      setName(restored?recovery.name:q.name);onRename(doc,q.name);setCaps(c);setWarehouses(w.items);
      setWarehouse(q.warehouseId||w.items.find(x=>x.state==="RUNNING")?.id||w.items[0]?.id||"");setCatalog(q.catalog||"");setSchema(q.schema||"");
      saved.current=doc.kind==="query-draft"?q:null;
      setParams(parameterNames(text.current).map(name=>({name,type:"STRING",value:""})));
      onDirty(doc,!!restored);
      if(restored)setNotice("Recovered local changes from this browser.");
      void queries.history().then(async h=>{const previous=h.items.find(r=>r.sourceRef===doc.ref);if(previous&&live){const detail=await queries.status(previous.id);if(live)setRun(detail);}}).catch(()=>{});
    }).catch(e=>{if(live)setError(e.message);});
    return()=>{live=false;if(bufferTimer.current)clearTimeout(bufferTimer.current);};
  },[doc.id,scope]);
  useEffect(()=>{if(!run||!ACTIVE_SQL.has(run.state)||run.state==="submission_unknown")return;
    let live=true;let timer:ReturnType<typeof setTimeout>;
    const poll=async()=>{try{const next=await queries.status(run.id);if(live){setRun(next);setRunError("");if(ACTIVE_SQL.has(next.state))timer=setTimeout(poll,document.hidden?15000:1000);}}catch(e){if(live){setRunError((e as Error).message);if (!(e instanceof ApiError && [401,403,404].includes(e.status))) timer=setTimeout(poll,5000);}}};
    timer=setTimeout(poll,1000);return()=>{live=false;clearTimeout(timer);};
  },[run?.id,run?.state]);
  useEffect(()=>{const before=(e:BeforeUnloadEvent)=>{if(source&&text.current!==source.text){e.preventDefault();e.returnValue="";}};window.addEventListener("beforeunload",before);return()=>window.removeEventListener("beforeunload",before);},[source]);
  function changed(value:string) {
    text.current=value;
    if(bufferTimer.current)clearTimeout(bufferTimer.current);
    bufferTimer.current=setTimeout(()=>{persist();onDirty(doc,value!==(source?.text??""));setGeneration(n=>n+1);
      setParams(old=>parameterNames(value).map(name=>old.find(p=>p.name===name)??{name,type:"STRING",value:""}));},180);
  }
  async function capture():Promise<SqlQuery> {
    const values={text:text.current,name,warehouseId:warehouse,catalog,schema,
      originQueryId:doc.kind==="query"?doc.ref:source?.originQueryId||"",...(saved.current?{version:saved.current.version}:{})};
    const draft=await queries.draft(values,saved.current?.id);saved.current=draft;return draft;
  }
  useEffect(() => {
    onCapture(async () => { const draft = await capture(); return { kind: "query-draft", ref: draft.id, name: draft.name }; });
    return () => onCapture(null);
  });
  async function execute() {
    if(busy||active)return;setBusy(true);setError("");setRunError("");
    try {
      const range=editor.current?.getSelection?.();
      if(range?.multiple)throw new Error("Use one contiguous selection to run SQL.");
      const draft=await capture();const snapshot=signature();
      const selected=range&&range.start!==range.end?text.current.slice(range.start,range.end):text.current;
      const usedNames=parameterNames(selected);
      const result=await queries.run(draft,{warehouseId:warehouse,catalog,schema},params.filter(p=>usedNames.includes(p.name)),crypto.randomUUID(),range&&range.start!==range.end?{start:range.start,end:range.end}:undefined);
      runInput.current=snapshot;setRun(result);setResultTab("results");setMobileTab("results");persist();
    }catch(e){setError((e as Error).message);}finally{setBusy(false);}
  }
  const saveCopy = () => {
    setSaveError("");
    try {const pending=pendingQueryCreate(scope,doc.id);setPendingCreate(!!pending);setSaveTarget({name:pending?.name??name,parent:pending?.parent??folder});setSaveDialog(true);}
    catch {setError("Create recovery storage is unavailable. Check Databricks for previous copies before creating a Query.");}
  };
  async function createCopy(savedName:string,parent:string) {
    if(busy)return;setBusy(true);setError("");
    let dispatched=false;
    try {
      let intent=pendingQueryCreate(scope,doc.id);
      if(!intent){
        const draft=await capture();
        intent={draft:{id:draft.id,version:draft.version},name:savedName,parent,key:crypto.randomUUID()};
        rememberQueryCreate(scope,doc.id,intent);
      }
      setPendingCreate(true);dispatched=true;
      const result=await queries.create(intent.draft,intent.name,intent.parent,intent.key);
      if(result.query){clearQueryCreate(scope,doc.id);setPendingCreate(false);setSaveDialog(false);clearQueryRecovery(scope,doc.id);onDirty(doc,false);onSaved(doc,result.query);}
      else if(result.state==="failed") {clearQueryCreate(scope,doc.id);setPendingCreate(false);setSaveError("The previous create was refused. Review the destination and try again.");}
      else setSaveError(result.state==="create_unknown"?"The Query may have been created. Check Databricks. Checking again preserves this request and will not create another copy.":"Creation is not yet verified. Check again to retrieve the same operation; it will not create another copy.");
    }catch(e){
      // A definitive precondition/auth refusal is safe to correct; a transport failure is uncertain.
      if(dispatched&&e instanceof ApiError&&[401,403,422].includes(e.status)){clearQueryCreate(scope,doc.id);setPendingCreate(false);}
      setSaveError(dispatched&&!(e instanceof ApiError)?"The create response was lost. The Query may already exist. Check again to recover this same request; it will not create another copy.":(e as Error).message);
    }finally{setBusy(false);}
  }
  async function attach() {setError("");try {const draft=await capture();onAttach({kind:"query-draft",ref:draft.id,name});setNotice("This SQL snapshot was added to your next message. Result rows and parameter values were not attached.");}catch(e){setError((e as Error).message);}}
  const native=doc.kind==="query"?workspaceUrl(workspace,{kind:"query",ref:doc.ref}):null;
  const stale=!!run&&(runInput.current?runInput.current!==signature():recoveredSqlInputsChanged(run,text.current,warehouse,catalog,schema));
  if(error&&!source)return <section className="sql-editor"><p className="sql-callout is-error" role="alert">{error}</p></section>;
  if(!source)return <p className="sql-loading" role="status">Opening SQL query…</p>;
  return <section className={`sql-editor mobile-${mobileTab}`} aria-label={`${name} SQL editor`} data-generation={generation}>
    <header className="sql-document-header"><div className="sql-document-identity"><span className="sql-type-badge">SQL</span><input className="sql-title-input" aria-label="Query name" value={name} maxLength={200} onChange={e=>{setName(e.target.value);onRename(doc,e.target.value);onDirty(doc,true);}}/><span className="sql-local-label">{doc.kind==="query"?(text.current!==source.text||name!==source.name?"Local changes":"Saved Query"):"Private draft"}</span></div><div className="sql-document-actions"><button className="btn" disabled={busy||!caps?.create||source.truncated} title={!caps?.create?caps?.createReason:undefined} onClick={()=>void saveCopy()}>{doc.kind==="query"?"Save copy":"Create Query"}</button><button className="btn ghost" onClick={()=>void attach()}>Add to chat</button>{native&&<a className="btn ghost" href={native} target="_blank" rel="noopener noreferrer">Open in Databricks ↗</a>}<button className="btn ghost" onClick={()=>void copyText(location.href).then(ok=>setNotice(ok?"Link copied":"Clipboard unavailable"))}>Copy link</button></div></header>
    <div className="sql-execution-bar"><button className="btn primary sql-run-button" disabled={busy||active||!warehouse||!caps?.run||source.canRun===false||source.truncated} title={source.runReason} onClick={()=>void execute()}>{busy?"Preparing…":selection?"▶ Run selection":"▶ Run query"}</button>{active&&<button className="btn" onClick={()=>void queries.cancel(run!.id).then(setRun).catch(e=>setRunError(e.message))}>Cancel</button>}<label className="sql-warehouse"><span className="sql-status-dot is-succeeded" aria-hidden/><select aria-label="SQL warehouse" value={warehouse} onChange={e=>setWarehouse(e.target.value)}><option value="">Choose a warehouse</option>{warehouses.map(w=><option key={w.id} value={w.id}>{w.name} · {w.state.toLowerCase()}</option>)}</select></label><span className="sql-viewer-identity">{caps?.demo?"Demo · ":""}Run as viewer <span aria-hidden>·</span> 1,000 row preview</span></div>
    <div className="sql-context-bar"><label>Catalog <input aria-label="SQL catalog" placeholder="Default catalog" value={catalog} onChange={e=>setCatalog(e.target.value)}/></label><span>/</span><label>Schema <input aria-label="SQL schema" placeholder="Default schema" value={schema} onChange={e=>setSchema(e.target.value)}/></label><span className="sql-context-note">{caps?.durable?"Encrypted run history":"Temporary drafts and history"}</span></div>
    {source.truncated&&<p className="sql-callout">Showing only the first 200 KiB. This source is read-only; open the complete Query in Databricks.</p>}
    {source.canRun===false&&<p className="sql-callout">{source.runReason}</p>}{!caps?.run&&<p className="sql-callout">{caps?.reason||"SQL execution is not enabled for this deployment."}</p>}
    {error&&<p className="sql-callout is-error" role="alert">{error}</p>}{runError&&<p className="sql-callout is-error" role="alert">{runError} <button className="btn" onClick={()=>void queries.status(run!.id).then(setRun).catch(e=>setRunError(e.message))}>Check status</button></p>}
    {notice&&<p className="sql-callout" role="status">{notice}<button className="sql-dismiss" aria-label="Dismiss SQL notice" onClick={()=>setNotice("")}>×</button></p>}
    {!storageOk&&<p className="sql-callout is-error" role="alert">Browser recovery storage is unavailable. Copy your SQL before closing.</p>}
    <div className="sql-mobile-tabs" role="group" aria-label="SQL workspace panels"><button aria-pressed={mobileTab==="editor"} onClick={()=>setMobileTab("editor")}>Editor</button><button aria-pressed={mobileTab==="results"} onClick={()=>setMobileTab("results")}>Results {run?.state==="succeeded"?"✓":""}</button></div>
    <div className="sql-source-pane"><Editor value={initial} language="sql" theme={theme} onChange={changed} onSave={()=>void saveCopy()} ariaLabel="SQL query source" readOnly={busy||source.truncated} onReady={host=>{editor.current=host;}} onCaret={()=>{const range=editor.current?.getSelection?.();setSelection(!!range&&range.start!==range.end);}} onChord={chord=>{if(chord==="run-stay"){void execute();return true;}return false;}}/>
      {!!params.length&&<fieldset className="sql-parameters"><legend>Parameters <span>Bound values · never interpolated into SQL</span></legend>{params.map((p,index)=><div className="sql-parameter" key={p.name}><label><span>:{p.name}</span><input aria-label={`Parameter ${p.name}`} disabled={p.value===null} placeholder="Enter a value" value={p.value??""} onChange={e=>setParams(old=>old.map((v,i)=>i===index?{...v,value:e.target.value}:v))}/></label><select aria-label={`Type of ${p.name}`} value={p.type} onChange={e=>setParams(old=>old.map((v,i)=>i===index?{...v,type:e.target.value}:v))}>{["STRING","INT","BIGINT","DECIMAL","DATE","TIMESTAMP"].map(t=><option key={t}>{t}</option>)}</select><label className="sql-null-toggle"><input type="checkbox" checked={p.value===null} onChange={e=>setParams(old=>old.map((v,i)=>i===index?{...v,value:e.target.checked?null:""}:v))}/>NULL</label></div>)}</fieldset>}
    </div>
    <div className="sql-output-pane"><div className="sql-output-tabs" role="group" aria-label="Query output"><button aria-pressed={resultTab==="results"} onClick={()=>setResultTab("results")}>Results {run?.result&&<span>{run.result.rowCount}</span>}</button><button aria-pressed={resultTab==="source"} onClick={()=>setResultTab("source")}>Executed SQL</button><span>SQL warehouse</span></div>{resultTab==="source"?<pre className="sql-executed-source">{run?.text||"Run a query to capture its immutable SQL snapshot."}</pre>:<SqlResults key={run?.id??"empty"} run={run} stale={stale} onAcknowledge={()=>void queries.acknowledge(run!.id).then(setRun).catch(e=>setRunError(e.message))} onCancel={()=>void queries.cancel(run!.id).then(setRun).catch(e=>setRunError(e.message))}/>}</div>
    {saveDialog&&<QuerySaveDialog name={saveTarget.name} folder={saveTarget.parent} copy={doc.kind==="query"} pending={pendingCreate} busy={busy} error={saveError} onClose={()=>setSaveDialog(false)} onSave={(title,parent)=>void createCopy(title,parent)}/>}
  </section>;
}
