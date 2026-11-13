import { chromium, expect } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { localApp } from './mission-test-server.mjs';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../../../..');
const iteration=process.env.ITERATION || 'work-01';
const shots=resolve(root,'specs/014-improve-agent/e2e/screenshots',iteration);mkdirSync(shots,{recursive:true});
const app=await localApp({agentWork:true});const browser=await chromium.launch();const errors=[],captures=[];
const post=(path,body={})=>app.json(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
async function session(scenario='workreview') { const s=await post('/api/sessions',{folder:'/Users/mission@example.test/agent_scratch',model:'fake/model-a'});await post(`/api/sessions/${s.id}/messages`,{text:`Update only cell 3 and verify the result. [[scenario:${scenario}]]`});return s.id; }
async function capture(page,name){await page.screenshot({path:resolve(shots,`${name}.png`)});captures.push(name);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();}
try{
 const sid=await session();const context=await browser.newContext({viewport:{width:1440,height:960},reducedMotion:'reduce'});const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));await page.goto(`${app.url}/#/session/${sid}`);
 await expect(page.getByRole('button',{name:'Apply change',exact:true})).toBeVisible({timeout:30000});await capture(page,'01-review-diff');
 await page.getByRole('tab',{name:'Changes',exact:true}).click();await expect(page.locator('.work-panel')).toContainText('print(300)');await capture(page,'02-changes');
 const pending=await app.json(`/api/sessions/${sid}/work`);expect(pending.change).toHaveLength(1);expect(pending.change[0].state).toBe('awaiting_review');
 await page.getByRole('button',{name:'Apply change',exact:true}).first().click();
 await expect.poll(async()=>(await app.json(`/api/sessions/${sid}/work`)).change[0].state,{timeout:30000}).toMatch(/applied|verified/);
 await expect(page.locator('.work-card').first()).toContainText(/applied|verified/);
 await expect.poll(async()=>(await app.json(`/api/sessions/${sid}`)).turns.at(-1).status,{timeout:30000}).toBe('completed');await capture(page,'03-applied');
 for(const tab of ['Runs','Assets','Capabilities','Resources','Budget']){await page.getByRole('tab',{name:tab,exact:true}).click();await expect(page.locator('.work-panel')).toBeVisible();await capture(page,`04-${tab.toLowerCase()}`);}
 await page.getByLabel('Limit',{exact:true}).fill('5000');await page.getByRole('button',{name:'Set budget'}).click();await expect(page.locator('.work-panel')).toContainText('5,000 tokens');
 await page.getByLabel('Autonomy mode').selectOption('plan');await expect.poll(async()=>(await app.json(`/api/sessions/${sid}/work`)).mode).toBe('plan');await expect(page.getByLabel('Autonomy mode')).toHaveValue('plan');await expect(page.getByLabel('Autonomy mode')).toBeEnabled();await capture(page,'05-plan-budget');
 await page.reload();await expect(page.getByLabel('Autonomy mode')).toHaveValue('plan');
 await page.getByLabel('Autonomy mode').selectOption('review');
 await page.getByRole('tab',{name:'Changes',exact:true}).click();await page.getByRole('button',{name:'Undo…'}).click();await page.getByRole('button',{name:'Confirm undo'}).click();await expect(page.locator('.work-card').first()).toContainText('reverted');await capture(page,'06-reverted');
 const rejected=await session();await page.goto(`${app.url}/#/session/${rejected}`);await expect(page.getByRole('button',{name:'Reject',exact:true})).toBeVisible({timeout:30000});await page.getByRole('button',{name:'Reject',exact:true}).click();await expect.poll(async()=>(await app.json(`/api/sessions/${rejected}/work`)).change[0].state).toBe('rejected');await expect(page.locator('.mission-state')).toHaveText('Stopped by your decision');await capture(page,'07-rejected');
 await page.setViewportSize({width:390,height:844});await page.getByRole('tab',{name:'Capabilities',exact:true}).click();await capture(page,'08-mobile-capabilities');
 expect(errors).toEqual([]);writeFileSync(resolve(shots,'../..',`${iteration}.json`),JSON.stringify({pass:true,captures,errors,scope:'Local app, actual ACP and MCP transports, encrypted SQLite; deterministic workspace fixture.'},null,2));console.log({pass:true,captures});
}finally{await browser.close();await app.stop();}
