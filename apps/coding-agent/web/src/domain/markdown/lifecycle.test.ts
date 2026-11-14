import { afterEach, expect, it, vi } from "vitest";
import { readingState, transition } from "./viewstate";
import { withMediaSlot, readRaster } from "./media";
import * as drafts from "../drafts";
afterEach(() => { vi.restoreAllMocks(); localStorage.clear(); drafts.configureDraftScope("local"); });
it("defers preview until composition ends and revocation always leaves reading", () => {
  let s=transition(readingState,{type:"edit"});
  s=transition(s,{type:"compositionStart"});s=transition(s,{type:"preview"});
  expect(s.mode).toBe("edit");expect(s.pendingPreview).toBe(true);
  s=transition(s,{type:"compositionEnd"});expect(s.mode).toBe("read");
  s=transition(s,{type:"permission",readOnly:true});expect(transition(s,{type:"edit"}).mode).toBe("read");
});
it("limits concurrent image bodies to four and removes cancelled waiters", async () => {
  let active=0,peak=0; const release: (()=>void)[]=[];
  const tasks=Array.from({length:4},()=>withMediaSlot(new AbortController().signal,async()=>{active++;peak=Math.max(peak,active);await new Promise<void>(r=>release.push(r));active--;}));
  const cancel=new AbortController();const waiting=withMediaSlot(cancel.signal,async()=>{throw new Error("must not start");}).catch(e=>e.message);
  cancel.abort();expect(await waiting).toMatch(/cancelled/);
  const next=withMediaSlot(new AbortController().signal,async()=>{active++;peak=Math.max(peak,active);active--;});
  release.splice(0).forEach(r=>r());await Promise.all([...tasks,next]);expect(peak).toBe(4);
});
it("rejects denied, oversized and unexpected image responses before decoding",async()=>{
  await expect(readRaster(new Response("",{status:403}))).rejects.toThrow(/permissions/);
  await expect(readRaster(new Response("<svg/>",{headers:{"Content-Type":"image/svg+xml"}}))).rejects.toThrow(/PNG/);
  await expect(readRaster(new Response("",{headers:{"Content-Type":"image/png","Content-Length":"6000000"}}))).rejects.toThrow(/5 MiB/);
});
it("isolates drafts by identity and expires active-tab recovery when storage fails",()=>{
  const now=Date.now();drafts.configureDraftScope("workspace:user-a");drafts.write({docId:"/a",text:"mine",at:now,basedOn:"v1"});
  drafts.configureDraftScope("workspace:user-b");expect(drafts.read("/a")).toBeNull();
  drafts.configureDraftScope("workspace:user-a");expect(drafts.read("/a")?.text).toBe("mine");
  vi.spyOn(Storage.prototype,"setItem").mockImplementation(()=>{throw new Error("quota");});
  expect(drafts.write({docId:"/b",text:"retained",at:now,basedOn:"v1"})).toBe(false);
  expect(drafts.read("/b",now)?.text).toBe("retained");expect(drafts.read("/b",now+drafts.TTL_MS+1)).toBeNull();
});
