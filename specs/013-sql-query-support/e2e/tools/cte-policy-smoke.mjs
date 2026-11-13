/** Exact screenshot SQL on a NEW draft, plus native/operator refusals and a real-model CTE mission. */
import {readFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {liveSession,evidence,expect} from './live-session.mjs';
const reproduction=JSON.parse(readFileSync(process.env.CTE_REPRODUCTION||'/private/tmp/opengenie-cte-reproduction.json','utf8'));
const reportFile=process.env.CTE_REPORT||'cte-report.json';
if(!/^[a-z-]+-report\.json$/.test(reportFile))throw Error('Invalid report filename');
const offset=Number(process.env.CTE_SCREENSHOT_OFFSET||0);
if(!Number.isSafeInteger(offset)||offset<0)throw Error('Invalid screenshot offset');
const s=await liveSession(),{deployment,origin,page,api}=s;
const screenshot=name=>s.screenshot(name.replace(/^\d+/,n=>String(Number(n)+offset)));
const checks=[],runs=[];let agent,originalBefore,initialWarehouseState;
const check=x=>{checks.push(x);console.log(`PASS ${x}`);};
const editor=()=>page.locator('.sql-source-pane .cm-content');
const results=()=>page.getByRole('region',{name:'Query results',exact:true});
async function sql(text){await editor().fill(text);await expect.poll(()=>editor().innerText()).toBe(text);await page.waitForTimeout(250);}
async function fresh(){
 await page.goto(origin+'/#/queries',{waitUntil:'domcontentloaded'});
 await expect(page.getByRole('heading',{name:'Queries',exact:true})).toBeVisible({timeout:45000});
 await page.keyboard.press('Meta+Shift+N');await page.getByRole('button',{name:'Queries',exact:true}).click();
 await page.getByRole('button',{name:'+ New SQL query',exact:true}).click();
 await expect(page.getByLabel('Query name')).toHaveValue('Untitled query',{timeout:30000});
 await expect(page.locator('.sql-editor .editor-host')).toHaveAttribute('data-status','ready');
}
async function submit(expected){
 const response=page.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname==='/api/sql/runs');
 await page.getByRole('button',{name:'▶ Run query',exact:true}).click();const r=await response;expect(r.status()).toBe(expected);return r.json();
}
async function events(sid){let after=0,out=[];for(;;){const p=await api(`/api/sessions/${sid}/events?after=${after}&limit=2000`);out.push(...p.events);if(!p.hasMore)return out;after=p.nextAfter;}}
try{
 expect((await api('/api/version')).version).toBe(deployment.version);await api('/api/ready');
 const me=await api('/api/me');expect(me.workspace.host).toBe(deployment.host);expect(me.demo).toBe(false);
 const caps=await api('/api/sql/capabilities');expect(caps).toMatchObject({run:true,durable:true,create:false,update:false});
 originalBefore=await api(`/api/sql/drafts/${reproduction.draft.id}`);
 initialWarehouseState=(await api('/api/sql/warehouses')).items.find(w=>w.id==='50b601f08d1a858d').state;
 check(`Exact dev release, identity and capability gates verified; warehouse initially ${initialWarehouseState}`);
 await page.setViewportSize({width:1920,height:1100});await fresh();
 await page.getByLabel('Query name').fill('CTE regression · daily taxi metrics');await sql(reproduction.draft.text);
 const first=await submit(202);expect(first.statementId).toBeTruthy();expect(first.sourceRef).not.toBe(reproduction.draft.id);runs.push({id:first.id,sourceRef:first.sourceRef,statementId:first.statementId,sourceHash:first.sourceHash});
 await screenshot('43-cte-native-submitted');
 await expect(page.locator('.sql-results [role=status]').first()).toHaveText('Succeeded',{timeout:150000});
 const run=await api(`/api/sql/runs/${first.id}`);expect(run.text).toBe(reproduction.draft.text);expect(run.result.rows.length).toBeGreaterThan(0);
 expect(run.result.columns.map(c=>c.name)).toEqual(['pickup_date','total_trips','avg_distance_miles','avg_fare_amount','avg_duration_minutes']);
 const days=run.result.rows.map(r=>r[0]);expect(new Set(days).size).toBe(days.length);expect([...days].sort()).toEqual(days);expect(run.result.rows.every(r=>Number(r[1])>0&&Number(r[2])>0&&Number(r[3])>0)).toBe(true);
 await expect(results().getByRole('table')).toBeVisible();await screenshot('44-cte-native-daily-results');
 check(`Exact CTE source succeeds natively: ${run.result.rowCount} daily rows, unique ordered dates, positive trip counts/distance/fare`);
 await page.getByRole('button',{name:/Colour theme:/}).click();await page.getByRole('menuitemcheckbox',{name:'Dark',exact:true}).click();await screenshot('45-cte-native-dark');
 await page.getByRole('button',{name:/Colour theme:/}).click();await page.getByRole('menuitemcheckbox',{name:'Light',exact:true}).click();
 const before=s.requests.filter(r=>r.method==='POST'&&r.path==='/api/sql/runs').length;
 await page.reload();await expect(results().getByRole('table')).toBeVisible({timeout:45000});expect(s.requests.filter(r=>r.method==='POST'&&r.path==='/api/sql/runs').length).toBe(before);
 expect((await api(`/api/sql/runs/${first.id}`)).statementId).toBe(first.statementId);
 check('Reload preserves the same CTE statement/result without another submission');
 await sql('SELECT preview_unreviewed_udf(1) WHERE 1 = 1 AND 2 = 2');const refusal=await submit(422);expect(refusal.detail.code).toBe('UNSUPPORTED_FUNCTION');
 await expect(page.getByRole('alert')).toContainText('Unrecognized or external function calls');await screenshot('46-cte-actionable-function-refusal');
 await sql('WITH x AS (SELECT 1) DELETE FROM must_never_be_touched');await submit(422);
 expect((await api('/api/sql/runs')).items.filter(r=>r.sourceRef===first.sourceRef)).toHaveLength(1);
 check('Unknown function and CTE mutation are refused before native submission; history still has one run');
 await sql(reproduction.draft.text);await page.getByRole('button',{name:'Add to chat',exact:true}).click();
 await page.reload();await expect(results().getByRole('table')).toBeVisible({timeout:45000});await expect(editor()).toContainText('WITH trip_metrics');
 await screenshot('47-cte-recovered-source-and-result');
 await page.setViewportSize({width:375,height:1000});await page.getByRole('group',{name:'SQL workspace panels'}).getByRole('button',{name:/^Results/}).click();await screenshot('49-cte-mobile-results');
 const pan=await page.locator('.sql-table-scroll').evaluate(el=>{el.scrollLeft=el.scrollWidth;const a=el.getBoundingClientRect(),b=el.querySelector('thead th:last-child').getBoundingClientRect();return {scrollable:el.scrollWidth>el.clientWidth,lastVisible:b.left>=a.left-1&&b.right<=a.right+1};});expect(pan.scrollable&&pan.lastVisible).toBe(true);
 await page.setViewportSize({width:1920,height:1100});
 check('CTE results and recovery controls render in light, dark and phone layouts');
 await fresh();
 const prompt='Inspect samples.nyctaxi.trips schema first and state the grain. Replace the attached query with one CTE named trip_metrics that computes pickup_date using date(), trip_distance, fare_amount and duration_minutes using ROUND((unix_timestamp(tpep_dropoff_datetime)-unix_timestamp(tpep_pickup_datetime))/60.0,2). Keep only trip_distance > 0 AND fare_amount > 0. Group by pickup_date to return COUNT(*) total_trips and ROUND(AVG(...),2) for the three metrics, ordered by pickup_date. Run the open query on the selected warehouse and report actual results. Do not create a notebook.';
 const response=page.waitForResponse(r=>r.request().method()==='POST'&&/\/api\/sessions\/[^/]+\/messages$/.test(new URL(r.url()).pathname));
 const composer=page.locator('.pane.assistant textarea');await composer.fill(prompt);await composer.press('Enter');const sent=await response;expect(sent.status()).toBe(202);
 const sid=new URL(sent.url()).pathname.split('/')[3],tid=(await sent.json()).turnId,qid=sent.request().postDataJSON().attachments.find(a=>a.kind==='query-draft').ref;
 agent={sid,tid,qid};let completed=false;
 for(let i=0;i<120;i++){
  const view=await api(`/api/sessions/${sid}`),turn=view.turns.find(t=>t.id===tid);
  if(turn&&!['queued','running','auditing'].includes(turn.status)){agent.status=turn.status;agent.model=view.model;expect(turn.status).toBe('completed');completed=true;break;}
  if(i%8===0)console.log('Waiting for real CTE model mission',turn?.status);await page.waitForTimeout(2000);
 }
 expect(completed).toBe(true);const log=await events(sid),names=new Map(log.filter(e=>e.type==='tool_call.started').map(e=>[e.callId,e.name]));
 agent.tools=log.filter(e=>e.type==='tool_call.updated'&&e.status==='completed').map(e=>names.get(e.callId));
 agent.receipts=log.filter(e=>e.type==='tool_call.updated'&&e.proof).map(e=>({name:names.get(e.callId),proof:e.proof}));
 expect(agent.tools).toContain('db_dbx_describe_table');expect(agent.tools.indexOf('db_dbx_describe_table')).toBeLessThan(agent.tools.indexOf('db_dbx_update_query'));
 const text=(await api(`/api/sql/drafts/${qid}`)).text;expect(text).toMatch(/WITH\s+trip_metrics/i);expect(text).toMatch(/unix_timestamp/i);expect(text).toMatch(/\bAND\b/i);
 const history=(await api('/api/sql/runs')).items.filter(r=>r.sourceRef===qid);expect(history).toHaveLength(1);const actual=await api(`/api/sql/runs/${history[0].id}`);expect(actual.state).toBe('succeeded');expect(actual.result.rowCount).toBeGreaterThan(0);
 const update=agent.receipts.find(x=>x.proof.action==='updated'),done=agent.receipts.find(x=>x.proof.state==='succeeded');expect(done.proof.sourceHash).toBe(update.proof.sourceHash);expect(done.proof.runId).toBe(actual.id);
 expect(log.filter(e=>e.type==='message.delta').map(e=>e.text).join('')).toMatch(/grain|one row per|each row/i);
 agent.evidence=log.filter(e=>e.type==='evidence.proposed').at(-1)?.rows;
 await expect(editor()).toContainText('trip_metrics',{timeout:20000});await expect(results().getByRole('table')).toBeVisible({timeout:30000});await screenshot('48-agent-cte-native-results');
 runs.push({id:actual.id,sourceRef:qid,statementId:actual.statementId,sourceHash:actual.sourceHash});check('Actual model inspects schema, authors the date/time CTE and executes the exact editor source successfully');
 const originalAfter=await api(`/api/sql/drafts/${reproduction.draft.id}`);expect(originalAfter.version).toBe(originalBefore.version);expect(originalAfter.text).toBe(originalBefore.text);
 expect(s.requests.some(r=>r.method!=='GET'&&r.path.includes(reproduction.draft.id))).toBe(false);
 check('Original user draft remains unchanged; only new test drafts were edited');
 expect(s.browserErrors).toEqual([]);expect(s.transportErrors).toEqual([]);check('No browser runtime or authenticated transport errors');
 writeFileSync(resolve(evidence,reportFile),JSON.stringify({success:true,version:deployment.version,gitCommit:deployment.gitCommit,deploymentId:deployment.deploymentId,initialWarehouseState,checks,runs,agent,originalDraftUnchanged:true,mobileLastColumnVerified:true,mobileCheckResubmissions:0,firstResult:{rowCount:run.result.rowCount,columns:run.result.columns.map(c=>c.name),grain:'one row per pickup date'},screenshots:s.screenshots,browserErrors:s.browserErrors,transportErrors:s.transportErrors,operations:'Original query read only; two native read-only CTE runs on new drafts; unknown function and mutation refused before native submission. No native Query asset writes.'},null,2)+'\n');
}catch(error){writeFileSync(resolve(evidence,reportFile),JSON.stringify({success:false,version:deployment.version,gitCommit:deployment.gitCommit,deploymentId:deployment.deploymentId,checks,runs,agent,error:String(error.stack||error),screenshots:s.screenshots,browserErrors:s.browserErrors,transportErrors:s.transportErrors},null,2)+'\n');throw error;}
finally{await s.browser.close();}
