/** Read-only verification of the deployed bundle. Fixture GETs never write workspace content. */
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';
const {chromium,expect}=createRequire(new URL('../../../apps/coding-agent/web/package.json',import.meta.url))('@playwright/test');
const base='https://coding-agent-7474647158015570.aws.databricksapps.com';
const token=JSON.parse(execFileSync('databricks',['auth','token','-p','opengenie-dev','-o','json'],{encoding:'utf8'})).access_token;
if(!token)throw new Error('Existing login did not provide a token');
const auth={Authorization:`Bearer ${token}`};
const meResponse=await fetch(base+'/api/me',{headers:auth});if(!meResponse.ok)throw new Error(`App identity check: ${meResponse.status}`);
const me=await meResponse.json();expect(me.username).toBe('raphael.mansuy@gmail.com');expect(me.workspace.host).toBe('https://dbc-cb61f1e1-bd8e.cloud.databricks.com');
const path=me.home+'/agent_scratch/notebook-md015-browser-fixture';
const text='# Notebook Markdown\nStyled reading is the default.\n\n## Verification\n- **Shared renderer**\n- Explicit Edit and Show preview\n\n| Check | Result |\n|---|---|\n| Served app | Ready |';
const browser=await chromium.launch();const ctx=await browser.newContext({viewport:{width:1440,height:1000},extraHTTPHeaders:auth,reducedMotion:'reduce'});const page=await ctx.newPage();const errors=[],blocked=[];
page.on('pageerror',e=>errors.push(e.message));
await page.route('**/api/**',async route=>{
 const request=route.request(),url=new URL(request.url());
 const json=d=>route.fulfill({contentType:'application/json',body:JSON.stringify(d)});
 if(url.pathname==='/api/workspace/object' && url.searchParams.get('path')===path)return json({path,name:'notebook-md015-browser-fixture',kind:'notebook',language:'PYTHON',truncated:false,version:'fixture-v1',cells:[{index:0,kind:'markdown',language:'markdown',source:text}]});
 if(url.pathname==='/api/workspace/version' && url.searchParams.get('path')===path)return json({version:'fixture-v1'});
 if(url.pathname==='/api/workspace/fence')return json({verdict:'allow',reason:'Read-only browser fixture',approval:null});
 if(request.method()!=='GET'){blocked.push(url.pathname);return route.abort();}
 return route.continue();
});
try{
 await page.goto(base+'/#/notebook'+path);const first=page.locator('.cell-block').first();await expect(first).toHaveAttribute('data-mode','read',{timeout:30000});await expect(first.locator('[data-heading-depth="1"]')).toHaveText('Notebook Markdown');
 for(const name of ['Hide the inspector','Hide the assistant','Hide the navigator']){const b=page.getByRole('button',{name,exact:true});if(await b.count())await b.first().click();}
 await expect(first.locator('table')).toBeVisible();const version=await page.locator('.app-version').textContent().catch(()=>page.locator('body').innerText());
 await page.screenshot({path:new URL('11-deployed-reading.png',import.meta.url).pathname});
 await first.getByRole('button',{name:'Edit Markdown cell 1',exact:true}).click();await expect(first.locator('.cm-content')).toBeVisible();await first.getByRole('button',{name:'Show preview of cell 1',exact:true}).click();await expect(first).toHaveAttribute('data-mode','read');expect(errors).toEqual([]);expect(blocked).toEqual([]);
 const scripts=await page.locator('script[src]').evaluateAll(nodes=>nodes.map(n=>n.src));
 writeFileSync(new URL('deployed-smoke.json',import.meta.url),JSON.stringify({pass:true,app:base,workspace:me.workspace.host,identity:me.username,version,scripts,errors,blocked,scope:'Real deployed frontend and API identity; notebook object is an intercepted fixture; no workspace writes or executions'},null,2));console.log('PASS deployed styled reading, source editor and preview; no workspace mutations');
}finally{await ctx.close();await browser.close();}
