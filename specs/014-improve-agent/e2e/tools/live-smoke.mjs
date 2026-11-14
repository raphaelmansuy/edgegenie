/** Live OAuth UI smoke; no prompt or workspace mutation. Requires the app's installed Playwright. */
import {createRequire} from 'node:module';
import {execFileSync} from 'node:child_process';
import {mkdirSync,writeFileSync,readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {resolve,dirname} from 'node:path';
const evidence=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const require=createRequire(resolve(evidence,'../../../apps/coding-agent/web/package.json'));
const {chromium,expect}=require('@playwright/test');
const token=JSON.parse(execFileSync('databricks',['auth','token','--profile','opengenie-dev','-o','json'],{encoding:'utf8'})).access_token;
const base='https://coding-agent-7474647158015570.aws.databricksapps.com';
const out=resolve(evidence,'screenshots/deployed-80e19d8-final');mkdirSync(out,{recursive:true});
async function request(path,options={}) {
 const response=await fetch(base+path,{...options,redirect:'error',headers:{Authorization:`Bearer ${token}`,'content-type':'application/json',...options.headers}});
 if(!response.ok)throw new Error(`${path}: HTTP ${response.status}`);
 return response.status===204?null:response.json();
}
const folder='/Users/raphael.mansuy@gmail.com/agent_scratch';
const session=await request('/api/sessions',{method:'POST',body:JSON.stringify({folder})});
const browser=await chromium.launch();const errors=[];const captures=[];
try {
 const context=await browser.newContext({viewport:{width:1440,height:960},reducedMotion:'reduce'});
 await context.route(base+'/**',route=>route.continue({headers:{...route.request().headers(),Authorization:`Bearer ${token}`}}));
 const page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
 await page.goto(`${base}/#/session/${session.id}`,{waitUntil:'domcontentloaded'});
 await expect(page.getByRole('textbox',{name:'Message the agent'})).toBeVisible({timeout:30000});
 await expect(page.getByRole('button',{name:'Conversation: Ready for the next question',exact:true})).toBeVisible({timeout:30000});
 await expect(page.getByRole('button',{name:'Model: gemini-3.8-flash',exact:true})).toBeVisible({timeout:30000});
 await expect(page.getByRole('region',{name:'Mission workspace',exact:true})).toContainText(folder,{timeout:30000});
 await expect(page.getByText('Loading conversations…',{exact:true})).toHaveCount(0,{timeout:30000});
 for(const [name,size] of [['01-desktop-ready.png',{width:1440,height:960}],['02-mobile-ready.png',{width:390,height:844}]]) {
  await page.setViewportSize(size);
  await expect(page.getByRole('heading',{name:'New session',exact:true})).toBeVisible();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();
  await page.screenshot({path:resolve(out,name)});captures.push(name);
 }
 expect(errors).toEqual([]);
 const version=await request('/api/version');
 const initialPath=resolve(evidence,'deployed-80e19d8-browser.json');
 const initial=JSON.parse(readFileSync(initialPath,'utf8'));initial.pass=false;initial.superseded='Initial screenshots preceded hydration. Final captures await ready status, model and folder using accessible regions.';
 writeFileSync(initialPath,JSON.stringify(initial,null,2)+'\n');
 const report={pass:true,captures,errors,version,scope:'Live user-OAuth app; actual default-model ACP session initialization and hydrated desktop/mobile rendering. No prompt sent or workspace object mutated.',harnessCorrections:['Autonomy control is gated in the deployed defaults; assert the visible composer instead.','Use the actual accessible Mission workspace region, not a nonexistent CSS class.']};
 writeFileSync(resolve(evidence,'deployed-80e19d8-final-browser.json'),JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify(report));
} finally {
 await browser.close();
 const response=await fetch(`${base}/api/sessions/${session.id}`,{method:'DELETE',headers:{Authorization:`Bearer ${token}`}});
 if(!response.ok)throw new Error(`Temporary session archive: HTTP ${response.status}`);
}
