import {chromium,expect} from '@playwright/test';
import {mkdirSync,writeFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {localApp} from './mission-test-server.mjs';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../../../..'),iteration=process.env.ITERATION||'storage-01',out=resolve(root,'specs/014-improve-agent/e2e/screenshots',iteration);mkdirSync(out,{recursive:true});
const app=await localApp({agentWork:true}),browser=await chromium.launch(),page=await browser.newPage({viewport:{width:1600,height:1000},reducedMotion:'reduce'}),captures=[],errors=[];
page.on('pageerror',e=>errors.push(e.message));
async function shot(name){await page.screenshot({path:resolve(out,name+'.png')});captures.push(name);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();}
try{
 const s=await app.json('/api/sessions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({folder:'/Users/mission@example.test/agent_scratch',model:'fake/model-a'})});
 let reads=0;page.on('request',r=>{if(r.url().endsWith('/storage'))reads++;});
 await page.goto(app.url+'/#/session/'+s.id);
 await page.getByRole('button',{name:'Show the inspector',exact:true}).click();await page.getByRole('tab',{name:'Audit',exact:true}).click();expect(reads).toBe(0);
 const summary=page.locator('.session-storage summary');await summary.focus();await page.keyboard.press('Enter');await expect(page.locator('.session-storage')).toContainText('Journal events');await shot('01-storage-desktop');
 const report=await app.json(`/api/sessions/${s.id}/storage`);expect(report.journal.eventRows).toBeGreaterThan(0);expect(report.measurement).toContain('excludes indexes');
 await page.getByRole('button',{name:'Refresh storage report'}).click();await expect(page.locator('.session-storage')).toContainText('Undo content');expect(reads).toBe(2);
 await page.setViewportSize({width:390,height:844});await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));const show=page.getByRole('button',{name:'Show the inspector',exact:true});if(await show.isVisible())await show.click();const audit=page.getByRole('tab',{name:'Audit',exact:true});await expect(audit).toBeVisible();if(await audit.getAttribute('aria-selected')!=='true')await audit.click();const details=page.locator('.session-storage');await expect(details).toBeVisible();if(await details.getAttribute('open')===null)await details.locator('summary').click();await expect(details).toContainText('Journal events');await details.scrollIntoViewIfNeeded();await shot('02-storage-mobile');
 // A failed read must remain visible and recover through an explicit refresh.
 await page.route('**/api/sessions/*/storage',r=>r.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Storage report is temporarily unavailable.'})}));
 await page.getByRole('button',{name:'Refresh storage report'}).click();await expect(page.locator('.session-storage [role=alert]')).toContainText('temporarily unavailable');await shot('03-storage-unavailable');
 await page.unroute('**/api/sessions/*/storage');await page.getByRole('button',{name:'Refresh storage report'}).click();await expect(page.locator('.session-storage')).toContainText('Journal events');await shot('04-storage-recovered');
 expect(errors).toEqual([]);writeFileSync(resolve(out,'../..',iteration+'.json'),JSON.stringify({pass:true,captures,errors,checks:{loadsOnDemand:true,refresh:true,keyboard:true,narrow:true,visibleFailure:true,recovery:true},scope:'Actual local app, shared SQLite journal/ledger, no workspace or model.'},null,2));console.log({pass:true,captures});
}catch(error){await shot('99-failed-state');writeFileSync(resolve(out,'../..',iteration+'.json'),JSON.stringify({pass:false,captures,error:String(error)},null,2));throw error;}finally{await browser.close();await app.stop();}
