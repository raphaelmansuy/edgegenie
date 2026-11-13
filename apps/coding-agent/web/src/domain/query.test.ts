import { describe, expect, it } from "vitest";
import { parameterNames, recoveredSqlInputsChanged, type SqlRun, rememberQuery, recoverQuery, pendingQueryCreate, rememberQueryCreate, clearQueryCreate } from "./query";
import { formatRoute, parseRoute, EMPTY_ROUTE } from "./route";
import { makeDoc } from "./docs";
import { parseWorkingSet } from "./workingset";
import { recentDocs, rememberDoc } from "./recent";
import { workspaceUrl } from "./links";

describe("SQL references and parameters",()=>{
  it("scans marker names without treating comments, literals or casts as bindings",()=>{
    expect(parameterNames("SELECT :region, :region, ':ignored', `:column`, 1::INT /* :x /* :y */ */ -- :z\n, :date")).toEqual(["region","date"]);
  });
  it("round trips query and private draft links without path normalization",()=>{
    const ref="00000000-0000-4000-8000-000000000001";
    for(const kind of ["query","query-draft"] as const){
      const route={...EMPTY_ROUTE,doc:{kind,ref}};
      expect(parseRoute(formatRoute(route))).toEqual(route);
      expect(makeDoc(kind,ref).ref).toBe(ref);
    }
    expect(parseRoute("#/queries").sql).toBe("queries");
    expect(parseRoute("#/query/12345")).toEqual(EMPTY_ROUTE);
  });
  it("restores query tabs and links native UUIDs using the documented handoff",()=>{
    const ref="00000000-0000-4000-8000-000000000001";
    const doc=makeDoc("query",ref);
    expect(parseWorkingSet(JSON.stringify({version:1,docs:[doc],active:doc.id})).docs).toHaveLength(1);
    expect(workspaceUrl({host:"https://workspace.test"},{kind:"query",ref})).toBe(`https://workspace.test/editor/queries/uuid/${ref}`);
    expect(workspaceUrl({host:"https://workspace.test"},{kind:"query-draft",ref})).toBeNull();
  });
  it("isolates recent query names across user/workspace scopes",()=>{
    rememberDoc({kind:"query",path:"00000000-0000-4000-8000-000000000001",name:"Private SQL"},"alice/workspace");
    expect(recentDocs("alice/workspace")[0].name).toBe("Private SQL");
    expect(recentDocs("bob/workspace")).toEqual([]);
  });
  it("isolates browser recovery by account/workspace scope",()=>{
    rememberQuery("alice/workspace","q","SELECT 1","Draft");
    expect(recoverQuery("alice/workspace","q")?.text).toBe("SELECT 1");
    expect(recoverQuery("bob/workspace","q")).toBeNull();
  });
  it("recovers the same create intent without persisting SQL or changing its operation key",()=>{
    const intent={draft:{id:"draft-id",version:3},name:"Revenue",parent:"/Users/alice",key:"same-request"};
    rememberQueryCreate("alice/workspace","q",intent);
    expect(pendingQueryCreate("alice/workspace","q")).toEqual(intent);
    expect(pendingQueryCreate("bob/workspace","q")).toBeNull();
    expect(Object.keys(pendingQueryCreate("alice/workspace","q")!.draft)).toEqual(["id","version"]);
    clearQueryCreate("alice/workspace","q");
    expect(pendingQueryCreate("alice/workspace","q")).toBeNull();
  });

  it("marks recovered output stale when context changes or private bindings were not recovered",()=>{
    const run={text:"SELECT 1",warehouseId:"w",catalog:"c",schema:"s"} as SqlRun;
    expect(recoveredSqlInputsChanged(run,"SELECT 1","w","c","s")).toBe(false);
    expect(recoveredSqlInputsChanged(run,"SELECT 1","other","c","s")).toBe(true);
    expect(recoveredSqlInputsChanged(run,"SELECT 1","w","c","other")).toBe(true);
    expect(recoveredSqlInputsChanged({...run,parameterNames:["secret"]},"SELECT 1","w","c","s")).toBe(true);
  });

});
