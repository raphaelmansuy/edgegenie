import { chromium,expect } from '@playwright/test';
import { mkdirSync,writeFileSync } from 'node:fs';
import { resolve,dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { localApp } from './mission-test-server.mjs';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../../../..');
const iteration=process.env.ITERATION||'operations-01';const shots=resolve(root,'specs/014-improve-agent/e2e/screenshots',iteration);mkdirSync(shots,{recursive:true});
const app=await localApp({agentWork:true,pgDsn:process.env.AGENT_E2E_PG_DSN}),browser=await chromium.launch();const captures=[],errors=[];
const post=(path,body={})=>app.json(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
async function create(){const s=await post('/api/sessions',{folder:'/Users/mission@example.test/agent_scratch',model:'fake/model-a'});await post(`/api/sessions/${s.id}/messages`,{text:'Run the notebook and inspect the saved result. [[scenario:workrun]]'});return s.id;}
async function open(sid,width=1440){const context=await browser.newContext({viewport:{width,height:960},reducedMotion:'reduce'}),page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));await page.goto(`${app.url}/#/session/${sid}`);return {context,page};}
async function shot(page,name){await page.screenshot({path:resolve(shots,`${name}.png`)});captures.push(name);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();}
try{
 const sid=await create();let {context,page}=await open(sid);await expect(page.getByRole('button',{name:'Run as me'})).toBeVisible({timeout:30000});await shot(page,'01-run-review');
 await page.getByRole('button',{name:'Run as me'}).click();await page.getByRole('tab',{name:'Runs',exact:true}).click();await expect(page.locator('.work-card')).toContainText('native_');await shot(page,'02-running');
 const work=await app.json(`/api/sessions/${sid}/work`);const oid=work.operation[0].id,native=work.operation[0].nativeId;
 await page.getByLabel(`Wake-up for ${oid}`).selectOption('continue');await context.close();
 // With every browser tab closed, the server observes the native run and queues one continuation.
 await expect.poll(async()=>(await app.json(`/api/sessions/${sid}/work`)).operation[0].state,{timeout:15000}).toBe('succeeded');
 await expect.poll(async()=>(await app.json(`/api/sessions/${sid}`)).turns.at(-1).status,{timeout:15000}).toBe('completed');
 ({context,page}=await open(sid));await page.getByRole('tab',{name:'Runs',exact:true}).click();await expect(page.locator('.work-card')).toContainText('succeeded');await page.getByText('Observed result',{exact:true}).click();await shot(page,'03-settled-return');await context.close();
 const before=await app.json(`/api/sessions/${sid}`);expect(before.turns).toHaveLength(2);
 await app.stop();await app.start();({context,page}=await open(sid));await page.getByRole('tab',{name:'Runs',exact:true}).click();await expect(page.locator('.work-card')).toContainText(native);await expect(page.locator('.work-card')).toContainText('succeeded');await expect(page.locator('.mission-state')).toHaveText('Achieved',{timeout:15000});await shot(page,'04-recovered');
 const after=await app.json(`/api/sessions/${sid}`);expect(after.turns).toHaveLength(2);
 // Startup maintenance prunes consumed scheduling rows. Its durable operation receipt
 // must still refuse a second continuation after the server process has been replaced.
 const rearm=await fetch(`${app.url}/api/sessions/${sid}/operations/${oid}/wakeup`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'continue'})});expect(rearm.status).toBe(409);expect(await rearm.text()).toContain('already fired');expect((await app.json(`/api/sessions/${sid}`)).turns).toHaveLength(2);await context.close();
 const cancel=await create();({context,page}=await open(cancel));await expect(page.getByRole('button',{name:'Run as me'})).toBeVisible({timeout:30000});await page.getByRole('button',{name:'Run as me'}).click();await page.getByRole('tab',{name:'Runs',exact:true}).click();await page.getByRole('button',{name:'Cancel run',exact:true}).click();await expect(page.locator('.work-card')).toContainText('cancelled');await expect(page.locator('.mission-state')).toHaveText('Stopped');await shot(page,'05-cancelled');
 await page.setViewportSize({width:390,height:844});await page.locator('.work-card').scrollIntoViewIfNeeded();await shot(page,'06-mobile-cancelled');
 expect(errors).toEqual([]);writeFileSync(resolve(shots,'../..',`${iteration}.json`),JSON.stringify({pass:true,captures,errors,scope:'Actual local app/ACP/MCP, durable journal and deterministic native runner. Browser closure, continuation, restart and cancellation.'},null,2));console.log({pass:true,captures});
}finally{await browser.close();await app.stop();}
