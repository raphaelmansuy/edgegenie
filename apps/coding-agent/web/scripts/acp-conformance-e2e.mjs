/** Spec 014: real HTTP -> orchestrator -> stdio ACP fixture -> durable journal -> browser. */
import { chromium, expect } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { localApp } from './mission-test-server.mjs';
const web=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const out=resolve(web,'../../../specs/014-improve-agent/e2e');
const iteration=process.env.ITERATION ?? 'iteration-01';
const shots=resolve(out,'screenshots',iteration);mkdirSync(shots,{recursive:true});
const app=await localApp();
const browser=await chromium.launch({headless:true});
const captures=[], errors=[];
async function create(scenario) {
 const s=await app.json('/api/sessions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({folder:'/Users/mission@example.test/agent_scratch',model:'fake/model-a'})});
 await app.json(`/api/sessions/${s.id}/messages`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:`Explain this protocol check. Do not use tools. [[scenario:${scenario}]]`})});
 return s.id;
}
async function open(id,width=1440,theme='light') {
 const context=await browser.newContext({viewport:{width,height:960},reducedMotion:'reduce'});
 await context.addInitScript(({theme})=>{localStorage.setItem('coding-agent:theme:v1',theme);}, {theme});
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 await page.goto(`${app.url}/#/session/${id}`);await expect(page.locator('.mission-title')).toBeVisible();
 return {context,page};
}
async function capture(page,name) {
 await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
 const audit=await page.evaluate(()=>({overflow:document.documentElement.scrollWidth>innerWidth+1,
   unnamed:[...document.querySelectorAll('button')].filter(e=>e.getClientRects().length&&!e.textContent.trim()&&!e.getAttribute('aria-label')&&!e.title).length}));
 expect(audit,name).toEqual({overflow:false,unnamed:0});
 const file=`${iteration}/${name}.png`;await page.screenshot({path:resolve(shots,`${name}.png`)});captures.push(file);
}
try {
 const sid=await create('approval');let {context,page}=await open(sid);
 await expect(page.getByRole('button',{name:'Allow once',exact:true})).toBeVisible();
 await expect(page.locator('.approval-input')).toContainText('/Shared/revenue_review');
 await expect(page.locator('.approval-input')).toContainText('SELECT 1');
 await capture(page,'01-permission-desktop');
 await page.getByRole('button',{name:'Deny',exact:true}).focus();await page.keyboard.press('Enter');
 await expect(page.locator('.mission-state')).toHaveText('Stopped by your decision');
 await expect(page.locator('.decision-stopped')).toBeVisible();
 await capture(page,'02-rejected-desktop');
 const events=await app.json(`/api/sessions/${sid}/events`);
 expect(events.events.filter(e=>e.type==='turn.declined')).toHaveLength(1);
 expect(events.events.filter(e=>e.type==='turn.auditing')).toHaveLength(0);
 await context.close();
 const approved=await create('approval');({context,page}=await open(approved));
 await page.getByRole('button',{name:'Allow once',exact:true}).click();
 await expect(page.locator('.mission-state')).toHaveText('Ready for review');await capture(page,'03-approved-desktop');await context.close();
 const meter=await create('usage');
 await expect.poll(async()=>(await app.json(`/api/sessions/${meter}`)).turns.at(-1).status).toBe('completed');
 ({context,page}=await open(meter));await expect(page.locator('.agent-meter')).toContainText('Context 2%');
 await expect(page.locator('.agent-meter')).toContainText('USD 0.0215');await capture(page,'04-meter-desktop');await context.close();
 for(const width of [390,320]) {
  const mobile=await create('approval');({context,page}=await open(mobile,width,'dark'));
  // The assistant is a drawer on narrow layouts; show the one existing decision surface.
  const allow=page.getByRole('button',{name:'Allow once',exact:true});
  if(!(await allow.isVisible())) {
   const conversation=page.getByRole('button',{name:/Open conversation|Show assistant|Open assistant/}).first();
   if(await conversation.count()) await conversation.click();
  }
  await expect(allow).toBeVisible();await expect(page.locator('html')).toHaveAttribute('data-theme','dark');await capture(page,`05-permission-${width}`);
  await page.getByRole('button',{name:'Deny',exact:true}).click();await context.close();
 }
 expect(errors).toEqual([]);
 writeFileSync(resolve(out,`acp-${iteration}.json`),JSON.stringify({pass:true,captures,pageErrors:errors,scope:'Local scripted agent. No workspace or model was contacted.'},null,2));
 console.log(JSON.stringify({pass:true,captures}));
} finally {await browser.close();await app.stop();}
