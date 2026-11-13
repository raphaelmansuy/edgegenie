/** Live dev smoke: actual responses, authenticated transport, no native SQL writes or execution. */
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const evidence=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const web=resolve(evidence,'../../../apps/coding-agent/web');
const {chromium,expect}=createRequire(resolve(web,'package.json'))('@playwright/test');
const deployment=JSON.parse(readFileSync(resolve(evidence,'deployment.json'),'utf8'));
const origin='https://coding-agent-7474647158015570.aws.databricksapps.com';
if(deployment.url!==origin||deployment.workspaceId!=='7474647158015570')throw new Error('Unexpected deployment target');
const token=JSON.parse(execFileSync('databricks',['auth','token','--profile',deployment.profile,'-o','json'],{encoding:'utf8',stdio:['ignore','pipe','pipe']})).access_token;
if(!token)throw new Error('Authenticated dev profile did not provide a token');
const authorization=`Bearer ${token}`;
const checks=[],screenshots=[],browserErrors=[],transportErrors=[];
const check=label=>{checks.push(label);console.log(`PASS ${label}`);};
const browser=await chromium.launch({headless:true});
const context=await browser.newContext({viewport:{width:1440,height:1000},deviceScaleFactor:1});
// Attach the credential only to the verified app origin; never follow redirects with it.
// Every fulfilled response is fetched from the real deployed app, without synthetic response bodies.
await context.route('**/*',async route=>{
  if(new URL(route.request().url()).origin!==origin)return route.abort('blockedbyclient');
  try{
    const response=await route.fetch({headers:{...route.request().headers(),authorization},maxRedirects:0,timeout:45000});
    if(response.status()>=300&&response.status()<400){transportErrors.push('Unexpected authenticated redirect');return route.abort('blockedbyclient');}
    await route.fulfill({response});
  }catch(error){transportErrors.push(`${route.request().method()} ${new URL(route.request().url()).pathname}: ${error.name}`);await route.abort('failed').catch(()=>{});}
});
const page=await context.newPage();
page.on('pageerror',error=>browserErrors.push(error.message));
async function api(path){
  const response=await context.request.get(origin+path,{headers:{authorization},maxRedirects:0});
  expect(response.status(),path).toBe(200);
  expect(response.headers()['content-type'],path).toContain('application/json');
  return response.json();
}
async function screenshot(name){
  await page.evaluate(()=>document.fonts.ready);
  await expect(page.locator('.sql-loading')).toHaveCount(0);
  if(await page.locator('.sql-editor').count())await expect(page.locator('.sql-editor .editor-host')).toHaveAttribute('data-status','ready');
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  const file=`screenshots/${name}.png`;const path=resolve(evidence,file);
  mkdirSync(dirname(path),{recursive:true});await page.screenshot({path,fullPage:true,animations:'disabled'});
  const bytes=readFileSync(path);screenshots.push({file,sha256:createHash('sha256').update(bytes).digest('hex')});
}
try{
  await api('/api/health');await api('/api/ready');
  const version=await api('/api/version');expect(version.version).toBe(deployment.version);
  check('Live health, readiness and expected release version return JSON 200');
  const me=await api('/api/me');
  expect(me.demo).toBe(false);expect(me.workspace.host).toBe(deployment.host);
  expect([deployment.user,'78760067054768@7474647158015570']).toContain(me.user);
  check('Live principal and workspace match the verified dev target');
  const openapi=await api('/openapi.json');
  for(const route of ['/api/sql/queries','/api/sql/drafts','/api/sql/runs','/api/sql/runs/{run_id}/cancel'])expect(openapi.paths[route],route).toBeTruthy();
  check('Live backend exposes SQL query, draft, execution and cancellation routes');
  const caps=await api('/api/sql/capabilities');
  expect(caps.demo).toBe(false);expect(caps.read).toBe(true);expect(caps.update).toBe(false);
  expect(caps.create).toBe(false);expect(caps.run).toBe(false);
  check('Native provider is active with create, run and update gates preserved');
  const listing=await api('/api/sql/queries?pageSize=1');expect(Array.isArray(listing.items)).toBe(true);
  check('Native query metadata is readable through the deployed user-authenticated API');
  await page.goto(origin+'/#/queries',{waitUntil:'domcontentloaded'});
  await expect(page.getByRole('heading',{name:'Queries',exact:true})).toBeVisible({timeout:45000});
  await expect(page.locator('.app-version')).toContainText(`v${deployment.version}`);
  await expect(page.locator('.sql-library [role=alert]')).toHaveCount(0);
  await screenshot('19-deployed-query-library');check('Live Queries route renders the native library');
  await page.getByRole('button',{name:'+ New SQL query',exact:true}).click();
  await expect(page.getByLabel('Query name')).toHaveValue('Untitled query');
  await expect(page.locator('.sql-source-pane .cm-content')).toContainText('SELECT 1 AS result');
  await expect(page.getByRole('button',{name:'▶ Run query',exact:true})).toBeDisabled();
  await expect(page.getByRole('button',{name:'Create Query',exact:true})).toBeDisabled();
  await screenshot('20-deployed-private-draft');check('Live editor creates an owner-scoped draft and respects server gates');
  await page.setViewportSize({width:375,height:900});
  await screenshot('21-deployed-mobile-draft');check('Live SQL authoring fits the 375px mobile viewport');
  await page.setViewportSize({width:1440,height:1000});
  await page.getByRole('button',{name:/Colour theme:/}).click();
  await page.getByRole('menuitemcheckbox',{name:'Dark',exact:true}).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme','dark');
  await screenshot('22-deployed-dark-draft');check('Live SQL editor and shell support the dark theme');
  expect(browserErrors).toEqual([]);expect(transportErrors).toEqual([]);check('No browser runtime or authenticated transport errors');
  writeFileSync(resolve(evidence,'deployed-report.json'),JSON.stringify({success:true,version:version.version,deploymentId:deployment.deploymentId,gitCommit:deployment.gitCommit,origin,checks,capabilities:caps,nativeMetadataPageSize:listing.items.length,screenshots,browserErrors,transportErrors,operations:'Read-only native APIs plus one private application draft; no native Query creation or SQL execution.'},null,2)+'\n');
}catch(error){
  writeFileSync(resolve(evidence,'deployed-report.json'),JSON.stringify({success:false,deploymentId:deployment.deploymentId,gitCommit:deployment.gitCommit,origin,error:String(error),checks,screenshots,browserErrors,transportErrors},null,2)+'\n');throw error;
}finally{await browser.close();}
