/** Prove a real dev app replacement resumes persisted SQL; never resubmit the query. */
import {readFileSync,writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {liveSession,evidence,expect} from './live-session.mjs';
const path=resolve(evidence,'deployed-report.json');
const report=JSON.parse(readFileSync(path,'utf8'));
if(!report.success||!report.recovery)throw Error('A successful SQL execution checkpoint is required');
const s=await liveSession();
try{
 expect(report.gitCommit).toBe(s.deployment.gitCommit);
 expect(report.deploymentId).not.toBe(s.deployment.deploymentId);
 const version=await s.api('/api/version');expect(version.version).toBe(s.deployment.version);
 const run=await s.api(`/api/sql/runs/${report.recovery.id}`);
 expect(run.state).toBe('succeeded');expect(run.statementId).toBe(report.recovery.statementId);
 expect(run.result.rows).toEqual([['1']]);
 const draft=await s.api(`/api/sql/drafts/${report.recovery.sourceRef}`);expect(draft.text).toBe('SELECT 1 AS result');
 expect(new URL(report.recovery.route).origin).toBe(s.origin);
 await s.page.goto(report.recovery.route,{waitUntil:'domcontentloaded'});
 await expect(s.page.getByRole('cell',{name:'1',exact:true})).toBeVisible({timeout:45000});
 await expect(s.page.locator('.sql-context-note')).toHaveText('Encrypted run history');
 expect(s.requests.filter(r=>r.method==='POST'&&r.path==='/api/sql/runs')).toHaveLength(0);
 expect(s.browserErrors).toEqual([]);expect(s.transportErrors).toEqual([]);
 await s.screenshot('33-native-server-restart-recovery');
 report.restartRecovery={fromDeploymentId:report.deploymentId,toDeploymentId:s.deployment.deploymentId,runId:run.id,statementId:run.statementId,draftId:draft.id,resubmissions:0,verified:true};
 report.executionDeploymentId=report.deploymentId;report.deploymentId=s.deployment.deploymentId;
 report.checks.push('Actual app redeployment recovers the same draft, statement handle and result without submission');
 report.screenshots.push(...s.screenshots);
 writeFileSync(path,JSON.stringify(report,null,2)+'\n');
 console.log('PASS Actual app redeployment preserves SQL source, statement identity and results; zero resubmissions');
}catch(error){report.success=false;report.recoveryError=String(error);writeFileSync(path,JSON.stringify(report,null,2)+'\n');throw error;}
finally{await s.browser.close();}
