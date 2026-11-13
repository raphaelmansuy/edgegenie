/** Live, user-owned isolated notebook fixture. No SQL or notebook execution. */
import {chromium,expect} from '@playwright/test';
import {mkdirSync,writeFileSync} from 'node:fs';
import {resolve,dirname} from 'node:path';
import {fileURLToPath} from 'node:url';
import {randomUUID} from 'node:crypto';
const root=resolve(dirname(fileURLToPath(import.meta.url)),'../../../..'),url=process.env.APP_URL;if(!url)throw new Error('APP_URL required');
const iteration=process.env.ITERATION||'live-edit-01';const out=resolve(root,'specs/014-improve-agent/e2e/screenshots',iteration);mkdirSync(out,{recursive:true});
async function json(path,body){const r=await fetch(url+path,body===undefined?undefined:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});if(!r.ok)throw new Error(path+': '+r.status+' '+await r.text());return r.json();}
const me=await json('/api/me');expect(me.username).toBe('raphael.mansuy@gmail.com');expect(me.workspace.host).toBe('https://dbc-cb61f1e1-bd8e.cloud.databricks.com');expect(me.demo).toBe(false);
const folder=me.home+'/agent_scratch/agent014-e2e-'+randomUUID().slice(0,8),path=folder+'/long-notebook';
await json('/api/workspace/mkdir',{path:folder});
const source='# Databricks notebook source\n'+Array.from({length:60},(_,i)=>`# CELL ${i}: preserve this exact cell\nprint("cell-${i}-${i===37?'BROKEN':'unchanged'}")\n`).join('\n# COMMAND ----------\n');
await json('/api/workspace/import',{parent:folder,name:'long-notebook',content:Buffer.from(source).toString('base64'),format:'SOURCE',language:'PYTHON'});
async function exported(){const r=await fetch(url+'/api/workspace/export?format=SOURCE&path='+encodeURIComponent(path));if(!r.ok)throw new Error('Export '+r.status);return r.text();}
const before=await exported(),cells=s=>s.split(/^# COMMAND -+\s*$/m);
const b=await chromium.launch(),p=await b.newPage({viewport:{width:1600,height:1000},reducedMotion:'reduce'});const captures=[],errors=[];p.on('pageerror',e=>errors.push(e.message));
const shot=async name=>{await p.screenshot({path:resolve(out,name+'.png')});captures.push(name);expect(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1)).toBeTruthy();};
let sid;
try{
 const session=await json('/api/sessions',{folder,model:'databricks/databricks-gpt-oss-120b'});sid=session.id;
 await json(`/api/sessions/${sid}/mode`,{mode:'review'});
 await json(`/api/sessions/${sid}/messages`,{text:`Fix only zero-based cell index 37 of notebook ${path}: replace the literal BROKEN with FIXED inside that cell, preserving every other byte and all other 59 cells. Read its revision and affected cell SHA, then use dbx_edit with one replace_cell operation for review. Do not run any notebook or SQL. After approval read back and verify the produced revision, with exact invocationId evidence.`});
 await p.goto(url+'/#/session/'+sid);await expect(p.getByRole('button',{name:'Apply change',exact:true})).toBeVisible({timeout:180000});expect(await exported()).toBe(before);await expect(p.locator('.mission-state')).toHaveText('Needs approval');await shot('01-real-review');
 await p.getByRole('button',{name:'Apply change',exact:true}).click();await expect.poll(async()=>(await json(`/api/sessions/${sid}/work`)).change[0].state,{timeout:90000}).toMatch(/applied|verified/);const after=await exported(),a=cells(before),c=cells(after);expect(a).toHaveLength(60);expect(c).toHaveLength(60);for(let i=0;i<60;i++)expect(c[i],`cell ${i}`).toBe(i===37?a[i].replace('BROKEN','FIXED'):a[i]);
 await p.getByRole('tab',{name:'Changes',exact:true}).click();await expect(p.locator('.work-card').first()).toContainText(/applied|verified/);await shot('02-real-applied');
 await expect.poll(async()=>(await json(`/api/sessions/${sid}`)).turns.at(-1).status,{timeout:90000}).toBe('completed');await p.getByRole('tab',{name:'Overview',exact:true}).click();await expect(p.locator('.mission-state')).toHaveText(/Achieved|Ready for review/);await shot('03-real-proof');
 await p.getByRole('tab',{name:'Changes',exact:true}).click();await p.getByRole('button',{name:'Undo…'}).click();await p.getByRole('button',{name:'Confirm undo'}).click();await expect(p.locator('.work-card').first()).toContainText('reverted');expect(await exported()).toBe(before);await shot('04-real-undo');
 expect(errors).toEqual([]);writeFileSync(resolve(out,'../..',iteration+'.json'),JSON.stringify({pass:true,captures,errors,sessionId:sid,workspace:me.workspace.host,folder,checks:{reviewWroteNothing:true,exactlyOneCellChanged:true,other59ByteIdentical:true,readBackVerified:true,undoByteIdentical:true},scope:'Real OpenCode 1.18.19, served gpt-oss-120b, actual app/ACP/MCP and user-owned Databricks notebook; no compute run.'},null,2));await json('/api/workspace/delete',{path:folder,recursive:true});console.log({pass:true,captures,sessionId:sid,folder,fixtureCleanup:'moved isolated folder to workspace trash'});
}finally{await b.close();}
