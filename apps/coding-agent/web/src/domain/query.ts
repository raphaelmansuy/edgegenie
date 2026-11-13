/** Query-specific values and one linear marker scan. The server is the execution policy boundary. */
export interface SqlQuery {
  id: string; name: string; text?: string; description?: string; owner?: string; modifiedAt?: string;
  warehouseId: string; catalog: string; schema: string; version?: number; originQueryId?: string;
  canRun?: boolean; runReason?: string; truncated?: boolean;
}
export interface SqlRun {
  id: string; state: string; name: string; sourceRef: string; sourceHash: string; text?: string;
  inputHash: string; warehouseId: string; createdAt: number; finishedAt?: number;
  catalog?:string; schema?:string;
  parameterNames?: string[]; error?: string; resultExpired?: boolean; cancelRequested?: boolean;
  result?: { columns: { name: string; type_text?: string }[]; rows: (string | null)[][]; truncated: boolean; rowCount: number; totalRows?: number };
}
export interface SqlCapabilities { demo: boolean; read: boolean; create: boolean; run: boolean; update: boolean; durable: boolean; reason: string; createReason: string }
export interface SqlParameter { name: string; type: string; value: string | null }
export interface SqlChange { version:number; runId:string; seq:number }
/** Apply remote source only while every local authoring input matches the captured snapshot. */
export function acceptsAgentQuery(local:{text:string;name:string;warehouseId:string;catalog:string;schema:string},saved:SqlQuery):boolean {
  return local.text===(saved.text??"")&&local.name===saved.name&&local.warehouseId===(saved.warehouseId??"")
    &&local.catalog===(saved.catalog??"")&&local.schema===(saved.schema??"");
}
/** Recovered bindings are deliberately absent, so do not imply their inputs still match. */
export function recoveredSqlInputsChanged(run:SqlRun,text:string,warehouse:string,catalog:string,schema:string):boolean {
  return text.trim()!==run.text?.trim()||warehouse!==run.warehouseId||catalog!==(run.catalog??"")||schema!==(run.schema??"")||!!run.parameterNames?.length;
}
/** Persist the exact create request before dispatch; an uncertain POST must never get a new key. */
export interface QueryCreateIntent { draft: Pick<SqlQuery,"id"|"version">; name:string; parent:string; key:string }
const createKey = (scope:string,id:string) => `opengenie:sql-create:${scope}:${id}`;
export function pendingQueryCreate(scope:string,id:string):QueryCreateIntent|null {
  const raw=localStorage.getItem(createKey(scope,id));
  if(!raw)return null;
  const value=JSON.parse(raw) as QueryCreateIntent;
  if(!value.draft?.id||!Number.isInteger(value.draft.version)||!value.key||typeof value.name!=="string"||typeof value.parent!=="string")
    throw new Error("The previous create request could not be recovered. Check Databricks before creating another copy.");
  return value;
}
export function rememberQueryCreate(scope:string,id:string,intent:QueryCreateIntent) {
  localStorage.setItem(createKey(scope,id),JSON.stringify(intent));
}
export function clearQueryCreate(scope:string,id:string) { localStorage.removeItem(createKey(scope,id)); }
export const ACTIVE_SQL = new Set(["submitting", "pending", "running", "cancel_requested", "reconciling", "submission_unknown"]);
export const sqlStateLabel = (state: string) => ({ pending: "Waiting for warehouse", running: "Running", succeeded: "Succeeded", failed: "Failed", canceled: "Canceled", cancel_requested: "Cancellation requested", submission_unknown: "Run outcome unknown", reconciling: "Checking run status" }[state] ?? state);

/** Skip SQL strings, quoted identifiers and comments before recognizing :name markers. */
export function parameterNames(text: string): string[] {
  const names = new Set<string>();
  for (let i = 0; i < text.length;) {
    if (text.startsWith("--", i)) { const end = text.indexOf("\n", i + 2); i = end < 0 ? text.length : end + 1; continue; }
    if (text.startsWith("/*", i)) {
      let depth = 1; i += 2;
      while (i < text.length && depth) {
        if (text.startsWith("/*", i)) { depth++; i += 2; }
        else if (text.startsWith("*/", i)) { depth--; i += 2; } else i++;
      }
      continue;
    }
    if ("'\"`".includes(text[i])) {
      const quote = text[i++];
      while (i < text.length) {
        if (text[i] === "\\") { i += 2; continue; }
        if (text[i++] === quote) { if (text[i] === quote) { i++; continue; } break; }
      }
      continue;
    }
    if (text[i] === ":" && text[i-1] !== ":" && /[A-Za-z_]/.test(text[i+1] ?? "")) {
      const start = ++i;
      while (i < text.length && /[A-Za-z0-9_]/.test(text[i])) i++;
      names.add(text.slice(start, i));
    } else i++;
  }
  return [...names].slice(0, 100);
}

const storageKey = (scope: string, id: string) => `opengenie:sql-draft:${scope}:${id}`;
export function recoverQuery(scope: string, id: string): { text: string; name: string; base?: string } | null {
  try {
    const value = JSON.parse(localStorage.getItem(storageKey(scope,id)) ?? "null");
    return value && Date.now()-value.at < 7*86400000 && typeof value.text === "string" && value.text.length < 204800
      && typeof value.name === "string" ? value : null;
  } catch { return null; }
}
export function rememberQuery(scope: string, id: string, text: string, name: string, base?: string): boolean {
  try { localStorage.setItem(storageKey(scope,id),JSON.stringify({text,name,base,at:Date.now()})); return true; }
  catch { return false; }
}
export function clearQueryRecovery(scope: string, id: string) { try { localStorage.removeItem(storageKey(scope,id)); } catch { /* blocked storage */ } }

export function favoriteQueries(scope: string): string[] {
  try { const raw = JSON.parse(localStorage.getItem(`opengenie:sql-favorites:${scope}`) ?? "[]"); return Array.isArray(raw) ? raw.filter(x => typeof x === "string").slice(0,1000) : []; }
  catch { return []; }
}
export function toggleQueryFavorite(scope: string, id: string): string[] {
  const old = favoriteQueries(scope); const next = old.includes(id) ? old.filter(x => x!==id) : [...old,id];
  try { localStorage.setItem(`opengenie:sql-favorites:${scope}`,JSON.stringify(next)); } catch { /* session still works */ }
  return next;
}
