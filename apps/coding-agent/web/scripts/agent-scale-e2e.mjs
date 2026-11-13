import {chromium, expect} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import {mkdirSync,writeFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {localApp} from './mission-test-server.mjs';
const web=resolve(dirname(fileURLToPath(import.meta.url)),'..'),root=resolve(web,'../../..');
const iteration=process.env.ITERATION||'scale-01', shots=resolve(root,'specs/014-improve-agent/e2e/screenshots',iteration);mkdirSync(shots,{recursive:true});
const app=await localApp({agentWork:true}),browser=await chromium.launch(),captures=[],errors=[];
const context=await browser.newContext({viewport:{width:1600,height:1000},reducedMotion:'reduce'}),page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
await page.addInitScript(()=>{window.__tasks=[];new PerformanceObserver(list=>{window.__tasks.push(...list.getEntries().map(e=>e.duration));}).observe({entryTypes:['longtask']});});
async function shot(name){await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));await page.screenshot({path:resolve(shots,name+'.png')});captures.push(name);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();}
try{
 const s=await app.json('/api/sessions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({folder:'/Users/mission@example.test/agent_scratch',model:'fake/model-a'})});
 await app.stop();execFileSync(resolve(web,'../.venv/bin/python'),[resolve(web,'scripts/agent-scale-seed.py'),resolve(app.scratch,'journal.sqlite'),s.id],{cwd:resolve(web,'..')});await app.start();
 const started=Date.now();await page.goto(`${app.url}/#/session/${s.id}`);await expect(page.locator('.mission-title')).toHaveText('Historical mission 200',{timeout:30000});
 await expect(page.locator('.dock-body .turn')).toHaveCount(30);await expect(page.locator('.dock-body .grid')).toHaveCount(30);await shot('01-recovered-200-turns');
 const frames=await page.evaluate(async()=>{const el=document.querySelector('.dock-body'),times=[];let last=performance.now();for(let i=0;i<60;i++){await new Promise(requestAnimationFrame);const now=performance.now();times.push(now-last);last=now;el.scrollTop=el.scrollHeight*(1-i/59);}return times.sort((a,b)=>a-b);});expect(frames[Math.floor(frames.length*.95)]).toBeLessThan(50);
 const earlier=page.getByRole('button',{name:'Show 30 earlier turns'});await earlier.scrollIntoViewIfNeeded();await earlier.click();await expect(page.locator('.dock-body .turn')).toHaveCount(30);await expect(page.locator('.dock-body .turn').first().locator('.prompt')).toContainText('Historical mission 141');await shot('02-earlier-results');
 while(await earlier.isEnabled()){await earlier.click();expect(await page.locator('.dock-body .turn').count()).toBeLessThanOrEqual(30);}
 await expect(page.locator('.dock-body .turn').first().locator('.prompt')).toHaveText('Historical mission 1');await expect(page.getByRole('navigation',{name:'Conversation history pages'})).toContainText('Viewing turns 1–20 of 200');expect(await page.locator('.dock-body .grid tbody tr').count()).toBeLessThanOrEqual(600);await shot('04-oldest-history-page');
 const firstResult=page.locator('.dock-body .grid-wrap').first();await firstResult.getByRole('button',{name:'Next result rows'}).click();await expect(firstResult).toContainText('Rows 21–40 of 100');await shot('05-result-row-page');await page.getByRole('button',{name:'Return to latest turn'}).click();await expect(page.locator('.dock-body .turn').last().locator('.prompt')).toContainText('Historical mission 200');
 // Switching conversation must reset the history window instead of inheriting a large expanded DOM.
 const fresh=await app.json('/api/sessions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({folder:'/Users/mission@example.test/agent_scratch',model:'fake/model-a'})});await page.goto(`${app.url}/#/session/${fresh.id}`);await expect(page.locator('.dock-body .turn')).toHaveCount(0);await page.goto(`${app.url}/#/session/${s.id}`);await expect(page.locator('.dock-body .turn')).toHaveCount(30);await expect(page.locator('.mission-title')).toHaveText('Historical mission 200');await expect(page.locator('.dock-body .turn').last().locator('.answer-block')).toContainText('Recovered mission 200');
 await page.setViewportSize({width:390,height:844});await shot('03-mobile-recovered');
 const tasks=await page.evaluate(()=>window.__tasks);expect(Math.max(0,...tasks)).toBeLessThan(2000);expect(errors).toEqual([]);
 writeFileSync(resolve(shots,'../../'+iteration+'.json'),JSON.stringify({pass:true,captures,errors,turns:200,rowsPerResult:100,columns:12,mountedTurnLimit:30,mountedRowsPerResult:20,scrollFrameP95Ms:frames[Math.floor(frames.length*.95)],worstTaskMs:Math.max(0,...tasks),elapsedMs:Date.now()-started,scope:'Actual local durable journal, HTTP/SSE replay, bounded history pages, result row pages, continuous scroll measurement and mobile.'},null,2));console.log({pass:true,captures,worstTaskMs:Math.max(0,...tasks),scrollFrameP95Ms:frames[Math.floor(frames.length*.95)]});
}finally{await browser.close();await app.stop();}
