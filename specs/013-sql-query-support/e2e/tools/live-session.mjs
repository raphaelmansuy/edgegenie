/** Shared live-test transport: real dev responses, credentials held only in memory. */
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {readFileSync,mkdirSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
export const evidence=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const web=resolve(evidence,'../../../apps/coding-agent/web');
export const {chromium,expect}=createRequire(resolve(web,'package.json'))('@playwright/test');
export async function liveSession(){
 const deployment=JSON.parse(readFileSync(resolve(evidence,'deployment.json'),'utf8'));
 const origin='https://coding-agent-7474647158015570.aws.databricksapps.com';
 if(deployment.url!==origin||deployment.workspaceId!=='7474647158015570')throw Error('Unexpected deployment target');
 const token=JSON.parse(execFileSync('databricks',['auth','token','--profile',deployment.profile,'-o','json'],{encoding:'utf8',stdio:['ignore','pipe','pipe']})).access_token;
 if(!token)throw Error('No authenticated dev token');
 const authorization=`Bearer ${token}`;
 const browser=await chromium.launch({headless:true});
 const context=await browser.newContext({viewport:{width:1440,height:1000},deviceScaleFactor:1});
 const transportErrors=[],browserErrors=[],requests=[],screenshots=[];
 await context.route('**/*',async route=>{
  if(new URL(route.request().url()).origin!==origin)return route.abort('blockedbyclient');
  // An EventSource never finishes. route.fetch buffers its body and prevents live UI updates.
  // Continue the genuine same-origin stream with auth instead of waiting for a finite response.
  if(route.request().headers().accept==='text/event-stream')return route.continue({headers:{...route.request().headers(),authorization}});
  try{
   const response=await route.fetch({headers:{...route.request().headers(),authorization},maxRedirects:0,timeout:45000});
   if(response.status()>=300&&response.status()<400)throw Error('Authenticated redirect refused');
   await route.fulfill({response});
  }catch(error){transportErrors.push(`${route.request().method()} ${new URL(route.request().url()).pathname}: ${error.name}`);await route.abort('failed').catch(()=>{});}
 });
 const page=await context.newPage();
 page.on('pageerror',error=>browserErrors.push(error.message));
 page.on('request',r=>{const p=new URL(r.url()).pathname;if(p.startsWith('/api/sql/'))requests.push({method:r.method(),path:p});});
 async function api(path){
  const r=await context.request.get(origin+path,{headers:{authorization},maxRedirects:0});
  expect(r.status(),path).toBe(200);expect(r.headers()['content-type'],path).toContain('application/json');return r.json();
 }
 async function screenshot(name){
  await page.evaluate(()=>document.fonts.ready);
  await expect(page.locator('.sql-loading')).toHaveCount(0);
  if(await page.locator('.sql-editor').count())await expect(page.locator('.sql-editor .editor-host')).toHaveAttribute('data-status','ready');
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));
  const file=`screenshots/${name}.png`,path=resolve(evidence,file);mkdirSync(dirname(path),{recursive:true});
  // Capture the actual screen. The application's editor/chat have independent scroll regions.
  await page.screenshot({path,fullPage:false,animations:'disabled'});
  screenshots.push({file,sha256:createHash('sha256').update(readFileSync(path)).digest('hex')});
 }
 return {deployment,origin,browser,context,page,api,screenshot,requests,screenshots,transportErrors,browserErrors};
}
