/** One typed SQL client, reusing the app's error/HTTP contract. */
import { call } from "./client";
import type { SqlCapabilities, SqlParameter, SqlQuery, SqlRun } from "../domain/query";
const json = { "Content-Type": "application/json" };
const body = (method: string, value: unknown, key?: string): RequestInit => ({method,headers:{...json,...(key ? {"Idempotency-Key":key} : {})},body:JSON.stringify(value)});
export const queries = {
  capabilities: () => call<SqlCapabilities>("/api/sql/capabilities"),
  list: (cursor = "", signal?: AbortSignal) => call<{items:SqlQuery[];nextCursor:string}>(`/api/sql/queries?cursor=${encodeURIComponent(cursor)}`,{signal}),
  get: (kind: string, id: string) => call<SqlQuery>(`/api/sql/${kind==="query" ? "queries" : "drafts"}/${encodeURIComponent(id)}`),
  draft: (value: Partial<SqlQuery>, id?: string) => call<SqlQuery>(`/api/sql/drafts${id ? `/${encodeURIComponent(id)}` : ""}`,body(id ? "PATCH" : "POST",value)),
  create: (draft:Pick<SqlQuery,"id"|"version">,name:string,parent:string,key:string) => call<{state:string;query?:SqlQuery;queryId?:string;operationId:string}>("/api/sql/queries",body("POST",{draftId:draft.id,version:draft.version,name,parent},key)),
  warehouses: () => call<{items:{id:string;name:string;state:string}[]}>("/api/sql/warehouses"),
  run: (draft:SqlQuery, context:{warehouseId:string;catalog:string;schema:string},parameters:SqlParameter[],key:string,selection?:{start:number;end:number}) => call<SqlRun>("/api/sql/runs",body("POST",{draftId:draft.id,version:draft.version,...context,parameters,selection},key)),
  status: (id:string) => call<SqlRun>(`/api/sql/runs/${encodeURIComponent(id)}`),
  cancel: (id:string) => call<SqlRun>(`/api/sql/runs/${encodeURIComponent(id)}/cancel`,{method:"POST"}),
  acknowledge: (id:string) => call<SqlRun>(`/api/sql/runs/${encodeURIComponent(id)}/acknowledge`,{method:"POST"}),
  history: () => call<{items:SqlRun[]}>("/api/sql/runs"),
};
