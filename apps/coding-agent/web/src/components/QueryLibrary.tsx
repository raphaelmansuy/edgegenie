import { useEffect, useState } from "react";
import { queries } from "../api/queries";
import { favoriteQueries, toggleQueryFavorite, sqlStateLabel, type SqlQuery, type SqlRun } from "../domain/query";
import { Database, Search } from "./Icons";

export function QueryLibrary({ scope,user,onOpen,onNew,onSnapshot }: {
  scope:string;user:string;onOpen:(q:SqlQuery)=>void;onNew:()=>void;onSnapshot:(text:string)=>void;
}) {
  const [items,setItems]=useState<SqlQuery[]>([]),[cursor,setCursor]=useState("");
  const [loading,setLoading]=useState(true),[error,setError]=useState("");
  const [filter,setFilter]=useState(""),[mine,setMine]=useState(false),[favoritesOnly,setFavoritesOnly]=useState(false);
  const [favorites,setFavorites]=useState(()=>favoriteQueries(scope));
  const [mode,setMode]=useState<"queries"|"history">("queries"),[history,setHistory]=useState<SqlRun[]>([]);
  const [evicted,setEvicted]=useState(false);
  async function load(next="",signal?:AbortSignal) {
    setLoading(true);setError("");
    try { const result=await queries.list(next,signal); if(signal?.aborted)return;
      setItems(old=>{const combined=[...new Map([...(next?old:[]),...result.items].map(q=>[q.id,q])).values()];if(combined.length>1000)setEvicted(true);return combined.slice(-1000);});setCursor(result.nextCursor);
    } catch(e) { if(!signal?.aborted)setError(String((e as Error).message)); } finally { if(!signal?.aborted)setLoading(false); }
  }
  useEffect(()=>{const controller=new AbortController();void load("",controller.signal);return()=>controller.abort();},[scope]);
  useEffect(()=>{if(mode==="history")void queries.history().then(r=>setHistory(r.items)).catch(e=>setError(e.message));},[mode]);
  const q=filter.trim().toLowerCase();
  const visible=items.filter(x=>(!mine||x.owner===user)&&(!favoritesOnly||favorites.includes(x.id))&&`${x.name} ${x.description??""}`.toLowerCase().includes(q));
  return <section className="sql-library" aria-label="SQL Queries">
    <div className="sql-library-heading"><div><span className="sql-eyebrow">SQL WORKSPACE</span><h2>Queries</h2><p>From a first question to SQL you can return to.</p></div><button className="btn primary" onClick={onNew}>+ New SQL query</button></div>
    <div className="sql-view-tabs" role="group" aria-label="SQL library view"><button aria-pressed={mode==="queries"} onClick={()=>setMode("queries")}>Saved queries <span>{items.length}</span></button><button aria-pressed={mode==="history"} onClick={()=>setMode("history")}>My run history</button></div>
    {error&&<div className="sql-callout is-error" role="alert">{error} <button className="btn" onClick={()=>void load()}>Try loading again</button></div>}
    {mode==="queries" ? <>
      <label className="sql-library-search"><Search size={17}/><input aria-label="Search cached queries" placeholder="Search queries by name or description…" value={filter} onChange={e=>setFilter(e.target.value)}/><kbd>SQL</kbd></label>
      <div className="sql-filter-row"><button className="sql-filter" aria-pressed={mine} onClick={()=>setMine(!mine)}>Owned by me</button><button className="sql-filter" aria-pressed={favoritesOnly} onClick={()=>setFavoritesOnly(!favoritesOnly)}>☆ Favorites <small>OpenGenie</small></button>{(filter||mine||favoritesOnly)&&<button className="btn ghost" onClick={()=>{setFilter("");setMine(false);setFavoritesOnly(false);}}>Clear filters</button>}<span className="sql-library-count" role="status">{visible.length} {visible.length===1?"query":"queries"}</span></div>
      {loading&&!items.length ? <p className="sql-loading" role="status">Loading accessible queries…</p> : visible.length ? <div className="sql-query-list">
        <div className="sql-list-labels" aria-hidden><span>QUERY</span><span>OWNER / UPDATED</span><span>FAVORITE</span></div>
        {visible.map(item=><article className="sql-query-row" key={item.id}><button className="sql-query-open" onClick={()=>onOpen(item)}><span className="sql-query-symbol" aria-hidden><Database size={18}/></span><span><strong>{item.name}</strong><small>{item.description||"Saved SQL Query"}</small></span></button><div className="sql-query-meta"><span>{item.owner===user?"You":item.owner||"Unknown owner"}</span><time>{item.modifiedAt?new Date(item.modifiedAt).toLocaleDateString(undefined,{month:"short",day:"numeric"}):"Unknown date"}</time></div><button className="sql-favorite" aria-label={`Favorite ${item.name}`} aria-pressed={favorites.includes(item.id)} onClick={()=>setFavorites(toggleQueryFavorite(scope,item.id))}>{favorites.includes(item.id)?"★":"☆"}</button></article>)}
      </div> : !error&&<div className="sql-library-empty"><Database size={30}/><h3>{q||mine||favoritesOnly?"No matching queries":"Your SQL work starts here"}</h3><p>{q||mine||favoritesOnly?"Try another search or clear your filters. Search covers cached pages.":"Create a query, choose your warehouse, and explore your first result."}</p><button className="btn" onClick={onNew}>New SQL query</button></div>}
      <footer className="sql-library-footer"><span>{items.length} queries in the cached search window{cursor?" · more pages available":""}{evicted?" · older pages evicted, search is partial":""}. {cursor?"Load more to discover other matches.":"Only assets accessible to you are listed."}</span>{cursor&&<button className="btn" disabled={loading} onClick={()=>void load(cursor)}>{loading?"Loading…":"Load more"}</button>}</footer>
      <aside className="sql-library-tip"><span className="sql-tip-symbol" aria-hidden>↳</span><div><strong>A query is more than its SQL.</strong><p>Keep the source, execution context, and run evidence together. Your assistant is one panel away.</p></div></aside>
    </> : <div className="sql-history-list">{!history.length?<div className="sql-library-empty"><h3>No SQL runs yet</h3><p>Run a query to see its execution record here.</p><button className="btn" onClick={onNew}>New SQL query</button></div>:history.map(run=><article className="sql-history-row" key={run.id}><div><strong>{run.name}</strong><small>{new Date(run.createdAt*1000).toLocaleString()}</small></div><span className={`sql-state-pill is-${run.state}`}>{sqlStateLabel(run.state)}</span><button className="btn" onClick={async()=>{try{const detail=await queries.status(run.id);if(detail.text)onSnapshot(detail.text);}catch(e){setError((e as Error).message);}}}>Open snapshot</button></article>)}</div>}
  </section>;
}
