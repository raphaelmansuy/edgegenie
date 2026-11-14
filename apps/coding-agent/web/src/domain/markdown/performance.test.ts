import { expect, it } from "vitest";
import { parseMarkdown } from "./parse";
import { readingState, transition, type ViewEvent } from "./viewstate";
it("records warmed adversarial parsing samples through the supported cell limit",()=>{
  const samples=[];
  for(const size of [1000,5000,10000,20000]){
    const input="\\(".repeat(size/2);parseMarkdown(input);const times=[];
    for(let i=0;i<7;i++){const at=performance.now();const model=parseMarkdown(input);times.push(performance.now()-at);expect(model.tree.type).toBe("root");}
    times.sort((a,b)=>a-b);samples.push({size,medianMs:Number(times[3].toFixed(2)),maxMs:Number(times[6].toFixed(2))});
  }
  console.info("MARKDOWN_PARSE_SAMPLES",JSON.stringify(samples));
  expect(samples.every(s=>s.medianMs<50)).toBe(true);
});
it("generated view event sequences cannot enter editing while permission is revoked",()=>{
  const events:ViewEvent[]=[{type:"edit"},{type:"preview"},{type:"compositionStart"},{type:"compositionEnd"},{type:"permission",readOnly:true},{type:"permission",readOnly:false}];
  for(let seed=1;seed<=100;seed++){let random=seed,state={...readingState};for(let n=0;n<100;n++){random=(Math.imul(random,1664525)+1013904223)>>>0;state=transition(state,events[random%events.length]);if(state.readOnly)expect(state.mode).toBe("read");}}
});
