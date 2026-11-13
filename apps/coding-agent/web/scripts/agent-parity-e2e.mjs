/** Production HTTP, stdio ACP, journal/SSE replay and bounded parity UI. */
import {chromium, expect} from '@playwright/test';
import {mkdirSync,writeFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {localApp} from './mission-test-server.mjs';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../../../..'),iteration=process.env.ITERATION||'parity-01',out=resolve(root,'specs/014-improve-agent/e2e/screenshots',iteration);mkdirSync(out,{recursive:true});
const app=await localApp({agentWork:true}),browser=await chromium.launch(),page=await browser.newPage({viewport:{width:1440,height:960},reducedMotion:'reduce'}),captures=[],errors=[];page.on('pageerror',error=>errors.push(error.message));
const post=(path,body)=>app.json(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
async function shot(name){await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));await page.screenshot({path:resolve(out,name+'.png')});captures.push(name);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();}
try {
 const session=await post('/api/sessions',{folder:'/Users/mission@example.test/agent_scratch',model:'fake/model-a'});
 await post(`/api/sessions/${session.id}/messages`,{text:'Explain these protocol notices. Do not use tools or change anything. [[scenario:parity]]'});
 await expect.poll(async()=>(await app.json(`/api/sessions/${session.id}`)).turns.at(-1).status).toBe('completed');
 await page.goto(app.url+'/#/session/'+session.id);
 const updates=page.getByRole('region',{name:'Agent updates'});await expect(updates).toContainText('Keep this conversation open');await expect(updates.locator('details')).toHaveCount(1);
 await updates.getByText('Context compaction · completed',{exact:true}).click();await expect(updates).toContainText('Retained the notebook revision.');await expect(updates).toContainText('pending review');await expect(updates).not.toContainText('temporary compaction error');await shot('01-parity-desktop');
 await page.reload();await expect(updates).toContainText('Credential expires soon');await expect(updates.locator('details')).toHaveCount(1);await updates.locator('summary').click();await expect(updates).toContainText('Retained the notebook revision.');await shot('02-parity-replayed');
 await page.setViewportSize({width:390,height:844});await expect(updates).toBeVisible();await shot('03-parity-mobile');
 await updates.locator('summary').focus();await page.keyboard.press('Enter');await expect(updates).toContainText('The pending review still needs your decision.');await shot('04-parity-mobile-expanded');
 expect(errors).toEqual([]);writeFileSync(resolve(out,'../..',iteration+'.json'),JSON.stringify({pass:true,captures,errors,checks:{warningDetailVisible:true,idBasedCompaction:true,appendSummary:true,omissionRetainsSummary:true,nullClearsError:true,replayKeepsOneCard:true,mobile:true},scope:'Actual local HTTP/stdio ACP/SQLite journal/SSE/browser with synthetic schema-shaped agent frames. No model or workspace contacted.'},null,2));console.log({pass:true,captures});
} catch(error){await shot('99-failed-state');writeFileSync(resolve(out,'../..',iteration+'.json'),JSON.stringify({pass:false,captures,error:String(error)},null,2));throw error;} finally{await browser.close();await app.stop();}
