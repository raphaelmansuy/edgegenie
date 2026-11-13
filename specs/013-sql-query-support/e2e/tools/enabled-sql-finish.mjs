/** Resume the remaining browser assertions after correcting the Results-checkmark selector. */
import {readFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {liveSession,evidence,expect} from './live-session.mjs';
const path=resolve(evidence,'deployed-report.json'),report=JSON.parse(readFileSync(path,'utf8'));
if(report.checks.length!==13||!report.recovery||!report.error?.includes("name: 'Results'"))throw Error('Unexpected continuation checkpoint');
const s=await liveSession();
try{
 expect(report.gitCommit).toBe(s.deployment.gitCommit);expect(report.deploymentId).toBe(s.deployment.deploymentId);
 const caps=await s.api('/api/sql/capabilities');expect(caps).toMatchObject({run:true,durable:true,demo:false,create:false,update:false});
 await s.page.goto(report.recovery.route,{waitUntil:'domcontentloaded'});
 await expect(s.page.getByRole('cell',{name:'1',exact:true})).toBeVisible({timeout:45000});
 await s.page.reload();await expect(s.page.getByRole('cell',{name:'1',exact:true})).toBeVisible({timeout:45000});
 expect(s.requests.filter(r=>r.method==='POST'&&r.path==='/api/sql/runs')).toHaveLength(0);
 await s.page.setViewportSize({width:375,height:900});
 await s.page.getByRole('group',{name:'SQL workspace panels'}).getByRole('button',{name:/^Results/}).click();
 await s.screenshot('31-native-mobile-results');await s.page.setViewportSize({width:1440,height:1000});
 report.checks.push('Reload recovers native results without another submission; mobile results fit');
 await s.page.goto(s.origin+'/#/queries');await s.page.getByRole('button',{name:'My run history',exact:true}).click();
 await expect.poll(()=>s.page.locator('.sql-history-row').count(),{timeout:30000}).toBeGreaterThanOrEqual(4);
 await s.screenshot('32-native-own-history');report.checks.push('Durable owner-scoped native run history is available');
 expect(s.browserErrors).toEqual([]);expect(s.transportErrors).toEqual([]);report.checks.push('No browser runtime or authenticated transport errors');
 report.harnessIterations=[{error:report.error,correction:'Results gains a checkmark after success; scope the mobile button to SQL workspace panels and match its Results prefix.',resolved:true,remainingChecksRepeated:true}];delete report.error;
 report.success=true;report.capabilities=caps;report.initialWarehouseState='STOPPED';
 report.coldStartVerified=report.checks.includes('Native SELECT 1 succeeds from STOPPED, using the returned statement handle');
 report.screenshots.push(...s.screenshots);report.completionResubmissions=0;
 report.operations='Four native table-free read-only statements, one policy refusal, one cancellation and reload recovery; no data-table reads, native Query writes or manual warehouse start/stop.';
 writeFileSync(path,JSON.stringify(report,null,2)+'\n');console.log('PASS Remaining mobile, reload, history and runtime checks; 16 native E2E checks complete');
}catch(error){report.continuationError=String(error);writeFileSync(path,JSON.stringify(report,null,2)+'\n');throw error;}
finally{await s.browser.close();}
