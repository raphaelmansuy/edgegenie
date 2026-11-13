/** Actual app/ACP/MCP, served model and SQL table; explicit review of only its owned fixture. */
import {chromium,expect} from '@playwright/test';
import {execFileSync} from 'node:child_process';
import {mkdirSync,writeFileSync,readFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../../../..'),url=process.env.APP_URL;if(!url)throw new Error('APP_URL required');
const iteration=process.env.ITERATION||'live-table-01',out=resolve(root,'specs/014-improve-agent/e2e/screenshots',iteration);mkdirSync(out,{recursive:true});
function fixture(...args){return JSON.parse(execFileSync(resolve(root,'apps/coding-agent/.venv/bin/python'),[resolve(root,'apps/coding-agent/scripts/agent-table-fixture.py'),...args],{encoding:'utf8',timeout:30000}));}
async function json(path,body){const response=await fetch(url+path,body===undefined?undefined:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!response.ok)throw new Error(path+': '+response.status+' '+await response.text());return response.json();}
const me=await json('/api/me');expect(me.username).toBe('raphael.mansuy@gmail.com');expect(me.workspace.host).toBe('https://dbc-cb61f1e1-bd8e.cloud.databricks.com');expect(me.demo).toBe(false);
const recovered=process.env.RECOVER_MANIFEST?JSON.parse(readFileSync(process.env.RECOVER_MANIFEST,'utf8')):null;const seeded=recovered?{schema:recovered.schema,table:recovered.table,folder:recovered.folder}:fixture('create');if(!recovered)await json('/api/workspace/mkdir',{path:seeded.folder});const s=recovered?{id:recovered.sessionId}:await json('/api/sessions',{folder:seeded.folder,schema:seeded.schema,model:'databricks/databricks-gpt-oss-120b'});if(!recovered)await json(`/api/sessions/${s.id}/mode`,{mode:'auto'});
const browser=await chromium.launch(),page=await browser.newPage({viewport:{width:1600,height:1000},reducedMotion:'reduce'}),captures=[],errors=[];page.on('pageerror',e=>errors.push(e.message));
async function shot(name){await page.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))));await page.screenshot({path:resolve(out,name+'.png')});captures.push(name);expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();}
try{
 if(!recovered)await json(`/api/sessions/${s.id}/messages`,{text:`Create exactly one empty Delta table ${seeded.table} with one column id BIGINT, using dbx_run_sql CREATE TABLE, then observe that operation with dbx_operation until it succeeds. This is an isolated schema owned by me. Do not use IF NOT EXISTS or OR REPLACE. Do not insert data, create any other object or clean anything up. Report that the table has no undo and cite actual invocation IDs.`});
 await page.goto(url+'/#/session/'+s.id);
 await expect.poll(async()=>(await json(`/api/sessions/${s.id}/work`)).resource.find(r=>r.asset.id===seeded.table)?.state,{timeout:240000}).toBe('present');
 const work=await json(`/api/sessions/${s.id}/work`);const operation=work.operation.find(r=>r.resourceIds?.length);expect(operation.state).toBe('succeeded');expect(work.resource.filter(r=>r.asset.id===seeded.table)).toHaveLength(1);expect(operation.undoAvailable).toBe(false);
 await expect.poll(async()=>(await json(`/api/sessions/${s.id}`)).turns.at(-1).status,{timeout:180000}).toMatch(/^(completed|blocked|failed)$/);
 const actual=fixture('inspect',seeded.schema);expect(actual.exists).toBe(true);expect(actual.owner).toBe(me.username);expect(actual.columns.map(c=>({...c,type:c.type.toLowerCase()}))).toEqual([{name:'id',type:'bigint'}]);
 await page.getByRole('tab',{name:'Runs',exact:true}).click();const runCard=page.locator('.work-card').filter({hasText:operation.nativeId});await expect(runCard).toContainText('This operation has no undo');await runCard.scrollIntoViewIfNeeded();await shot('01-native-table-run');
 await page.getByRole('tab',{name:'Resources',exact:true}).click();await expect(page.locator('.work-card').first()).toContainText(seeded.table);await shot('02-native-table-resource');
 await page.getByRole('button',{name:'Review cleanup',exact:true}).click();expect(fixture('inspect',seeded.schema).exists).toBe(true);await expect(page.getByRole('button',{name:'Confirm deletion',exact:true})).toBeVisible();await shot('03-table-cleanup-review');
 await page.getByRole('button',{name:'Confirm deletion',exact:true}).click();await expect(page.locator('.work-card').first()).toContainText('deleted',{timeout:30000});expect(fixture('inspect',seeded.schema).exists).toBe(false);await shot('04-native-table-deleted');expect(errors).toEqual([]);
 fixture('cleanup',seeded.schema);await json('/api/workspace/delete',{path:seeded.folder,recursive:true});
 writeFileSync(resolve(out,'../..',iteration+'.json'),JSON.stringify({pass:true,captures,errors,recoveredFrom:process.env.RECOVER_MANIFEST||null,sessionId:s.id,...seeded,nativeTableId:actual.tableId,checks:{actualModelSql:true,oneCreatedResource:true,noUndoExplicit:true,reviewWroteNothing:true,nativeAbsenceAfterCleanup:true,emptySchemaRemoved:true},scope:'Real model/app/ACP/MCP; native SQL as current user and reviewed deletion of exactly its isolated table.'},null,2));console.log({pass:true,captures,sessionId:s.id,...seeded});
}catch(error){await shot('99-failed-state');writeFileSync(resolve(out,'../..',iteration+'.json'),JSON.stringify({pass:false,captures,error:String(error),sessionId:s.id,...seeded},null,2));throw error;}finally{await browser.close();}
