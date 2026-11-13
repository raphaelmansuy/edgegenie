/** Review the product UI for completed app-path exam records, including failed model work. */
import {chromium,expect} from '@playwright/test';
import {mkdirSync,readFileSync,readdirSync,writeFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../../../..');
const app=process.env.APP_URL;if(!app)throw new Error('APP_URL is required');
const batch=process.env.BATCH||'agent014-proof-M9-app', iteration=process.env.ITERATION||'exam-proof-01';
const directory=resolve(root,'exams/results',batch), shots=resolve(root,'specs/014-improve-agent/e2e/screenshots',iteration);mkdirSync(shots,{recursive:true});
const records=readdirSync(directory).filter(n=>n.endsWith('.json')).map(n=>JSON.parse(readFileSync(resolve(directory,n),'utf8')));
const browser=await chromium.launch(),context=await browser.newContext({viewport:{width:1600,height:1000},reducedMotion:'reduce'}),page=await context.newPage(),captures=[],errors=[];page.on('pageerror',e=>errors.push(e.message));
async function shot(name){await page.screenshot({path:resolve(shots,name+'.png')});captures.push(name);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();expect(await page.locator('.blocked').evaluateAll(nodes=>nodes.every(n=>n.scrollWidth<=n.clientWidth+1))).toBeTruthy();}
try{
 for(const result of records){
  expect(result.via).toBe('app');expect(result.valid).not.toBe(false);
  const label=result.model.includes('maverick')?'maverick':'gpt-oss';
  await page.setViewportSize({width:1600,height:1000});await page.goto(`${app}/#/session/${result.session_id}`);
  if(result.turn_status==='blocked')await expect(page.locator('.mission-state')).toHaveText('Blocked',{timeout:30000});
  else await expect(page.locator('.mission-state')).toHaveText(/Achieved|Ready for review/,{timeout:30000});
  const folded=page.locator('.tools-head[aria-expanded="false"]');if(await folded.count())await folded.first().click();
  await expect(page.locator('.dock-body .tool-row')).toHaveCount(result.tool_calls);await expect(page.locator('.mission-proof').first()).toBeAttached();
  await shot(label+'-overview');
  if(result.turn_status==='completed'){
   await page.getByRole('tab',{name:'Changes',exact:true}).click();await expect(page.locator('.work-card').first()).toContainText('verified');await shot(label+'-change');
  }else{
   await page.setViewportSize({width:390,height:844});await shot(label+'-mobile-blocked');
  }
 }
 expect(errors).toEqual([]);writeFileSync(resolve(shots,'../../'+iteration+'.json'),JSON.stringify({pass:true,captures,errors,records:records.map(r=>({model:r.model,sessionId:r.session_id,status:r.turn_status,score:r.score,total:r.total})),scope:'Actual app-path exam sessions with served models. No live workspace resource is changed by this UI review.'},null,2));console.log({pass:true,captures});
}finally{await browser.close();}
