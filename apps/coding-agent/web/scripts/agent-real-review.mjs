/** Inspect saved read-only real-model qualification; never dispatch a model or workspace write. */
import {chromium,expect} from '@playwright/test';
import {readFileSync,mkdirSync,writeFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../../../..');
const url=process.env.APP_URL;if(!url)throw new Error('APP_URL must name the local identity-verified qualification app');
const out=resolve(root,'specs/014-improve-agent/e2e/screenshots/real-agent-03');mkdirSync(out,{recursive:true});
const b=await chromium.launch(),p=await b.newPage({viewport:{width:1440,height:960},reducedMotion:'reduce'});const errors=[],captures=[];p.on('pageerror',e=>errors.push(e.message));
const shot=async name=>{await p.screenshot({path:resolve(out,name+'.png')});captures.push(name);expect(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();};
try{
 for(const model of ['databricks-llama-4-maverick','databricks-gpt-oss-120b']){
  const d=JSON.parse(readFileSync(resolve(root,'specs/014-improve-agent/e2e/real-agent',model+'-03.json')));expect(d.status).toBe('completed');await p.goto(url+'/#/session/'+d.session_id);await expect(p.locator('.mission-state')).toHaveText('Achieved',{timeout:20000});await p.locator('.mission-proof > summary').click();await shot(model);
 }
 await p.getByRole('tab',{name:'Capabilities',exact:true}).click();await expect(p.locator('.work-table')).toContainText('Unity Catalog');await p.locator('.work-table').scrollIntoViewIfNeeded();await shot('capabilities-desktop');
 await p.emulateMedia({colorScheme:'dark'});await p.setViewportSize({width:390,height:844});await shot('capabilities-dark-390');expect(errors).toEqual([]);writeFileSync(resolve(out,'../../real-agent-03-ui.json'),JSON.stringify({pass:true,errors,captures,scope:'Two real models, local app linked to the verified Databricks workspace; read-only capability proof.'},null,2));console.log({pass:true,captures});
}finally{await b.close();}
