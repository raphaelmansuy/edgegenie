import { chromium,expect } from '@playwright/test';
import { mkdirSync,writeFileSync } from 'node:fs';
import { resolve,dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { localApp } from './mission-test-server.mjs';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../../../..');const iteration=process.env.ITERATION||'questions-01';const shots=resolve(root,'specs/014-improve-agent/e2e/screenshots',iteration);mkdirSync(shots,{recursive:true});
const app=await localApp({agentWork:true}),browser=await chromium.launch();const errors=[],captures=[];
const post=(path,body={})=>app.json(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
async function create(){const s=await post('/api/sessions',{folder:'/Users/mission@example.test/agent_scratch',model:'fake/model-a'});await post(`/api/sessions/${s.id}/messages`,{text:'Ask which approach to use. Do not use tools. [[scenario:question]]'});return s.id;}
const context=await browser.newContext({viewport:{width:1440,height:960},reducedMotion:'reduce'});const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
async function shot(name){await page.screenshot({path:resolve(shots,name+'.png')});captures.push(name);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();}
try{
 let sid=await create();await page.goto(`${app.url}/#/session/${sid}`);await expect(page.getByRole('form',{name:'Agent question'})).toBeVisible({timeout:30000});await expect(page.getByLabel('Review approach')).toHaveValue('Focused change');await shot('01-question');
 await page.getByLabel('Additional constraints').fill('Keep existing cell boundaries.');await page.getByRole('button',{name:'Send response'}).focus();await page.keyboard.press('Enter');await expect(page.locator('.mission-state')).toHaveText('Ready for review');await expect(page.locator('.mission-outcome-text')).toContainText('accept');await shot('02-answered');
 sid=await create();await page.goto(`${app.url}/#/session/${sid}`);await expect(page.getByRole('button',{name:'Skip question'})).toBeVisible({timeout:30000});await page.getByRole('button',{name:'Skip question'}).click();await expect(page.locator('.mission-outcome-text')).toContainText('decline');await shot('03-skipped');
 sid=await create();await page.goto(`${app.url}/#/session/${sid}`);await expect(page.getByRole('form',{name:'Agent question'})).toBeVisible({timeout:30000});await app.stop();await app.start();await page.reload();await expect(page.locator('.work-question')).toContainText('expired');await expect(page.locator('.mission-state')).toHaveText('Restore needed');await expect(page.getByRole('button',{name:'Send response'})).toHaveCount(0);await shot('04-expired');
 await page.setViewportSize({width:390,height:844});const mobile=await create();await page.goto(`${app.url}/#/session/${mobile}`);const form=page.getByRole('form',{name:'Agent question'});if(!await form.isVisible())await page.getByRole('button',{name:/Open conversation|Show assistant/}).first().click();await expect(form).toBeVisible({timeout:30000});await shot('05-mobile-question');await page.getByRole('button',{name:'Cancel',exact:true}).click();await expect(page.locator('.mission-outcome-text')).toContainText('cancel');
 expect(errors).toEqual([]);writeFileSync(resolve(shots,'../..',iteration+'.json'),JSON.stringify({pass:true,captures,errors},null,2));console.log({pass:true,captures});
}finally{await browser.close();await app.stop();}
