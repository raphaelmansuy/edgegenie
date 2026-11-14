import {chromium,expect} from '@playwright/test';
import {writeFileSync} from 'node:fs';
import {resolve} from 'node:path';
import {localApp} from './mission-test-server.mjs';
const out=resolve('../../../specs/015-notebook-md/e2e');
const app=await localApp(),browser=await chromium.launch(),page=await browser.newPage({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
const first='/Users/mission@example.test/agent_scratch/KPI résumé #1',second='/Users/mission@example.test/agent_scratch/notes.py';
const errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.addInitScript(()=>{window.copied=[];window.denyCopy=false;Object.defineProperty(navigator,'clipboard',{value:{writeText:async value=>{if(window.denyCopy)throw new Error('denied');window.copied.push(value);}},configurable:true});document.execCommand=()=>false;});
await page.route('**/api/**',route=>{const u=new URL(route.request().url()),p=u.pathname;const json=d=>route.fulfill({contentType:'application/json',body:JSON.stringify(d)});const path=u.searchParams.get('path');if(p==='/api/workspace/object')return json({path,name:path.split('/').at(-1),kind:path===first?'notebook':'file',language:'PYTHON',truncated:false,version:'v1',cells:[{index:0,kind:'markdown',language:'markdown',source:'# KPI dashboard\nReadable Markdown.'}],text:'# Notes'});if(p==='/api/workspace/version')return json({path,version:'v1'});if(p==='/api/workspace/fence')return json({verdict:'allow',reason:'Test folder',approval:null});return route.continue();});
const hash=(kind,path)=>'#/'+kind+'/'+path.slice(1).split('/').map(p=>encodeURIComponent(p).replace(/%40/g,'@')).join('/');
try{
 await page.goto(app.url+'/'+hash('notebook',first));await expect(page.locator('.notebook-markdown')).toBeVisible();
 await page.evaluate(h=>location.hash=h,hash('file',second));await expect(page.locator('.doc-tab')).toHaveCount(2);
 const before=page.url(),tab=page.getByRole('tab',{name:/KPI résumé/});await tab.click({button:'right'});await expect(page.getByRole('menuitem',{name:'Copy URL',exact:true})).toBeVisible();await page.screenshot({path:resolve(out,'12-tab-copy-menu.png')});
 await page.getByRole('menuitem',{name:'Copy URL',exact:true}).click();await expect.poll(()=>page.evaluate(()=>window.copied.at(-1))).toBe(app.url+'/'+hash('notebook',first));expect(page.url()).toBe(before);await expect(page.getByText('Link copied',{exact:true})).toBeVisible();
 await tab.click({button:'right'});await page.getByRole('menuitem',{name:'Copy full path',exact:true}).click();await expect.poll(()=>page.evaluate(()=>window.copied.at(-1))).toBe(first);expect(page.url()).toBe(before);
 await page.getByRole('button',{name:'Tab actions',exact:true}).click();await page.getByRole('menuitem',{name:'Copy full path',exact:true}).click();await expect.poll(()=>page.evaluate(()=>window.copied.at(-1))).toBe(second);
 await page.evaluate(()=>window.denyCopy=true);await page.getByRole('button',{name:'Tab actions',exact:true}).click();await page.getByRole('menuitem',{name:'Copy full path',exact:true}).click();await expect(page.getByText('Could not copy the full path',{exact:true})).toBeVisible();
 await expect(page.getByText('Could not copy the full path',{exact:true})).not.toBeVisible({timeout:10000});await page.setViewportSize({width:390,height:400});await page.getByRole('button',{name:'Tab actions',exact:true}).click();const box=await page.getByRole('menu').boundingBox();expect(box.y).toBeGreaterThanOrEqual(8);expect(box.y+box.height).toBeLessThanOrEqual(393);expect(await page.getByRole('menu').evaluate(el=>{const r=el.getBoundingClientRect();return !!document.elementFromPoint(r.left+12,r.top+12)?.closest('.tab-menu');})).toBe(true);await page.screenshot({path:resolve(out,'13-tab-copy-menu-narrow.png')});await page.keyboard.press('Escape');await expect(page.getByRole('menu')).toHaveCount(0);expect(errors).toEqual([]);
 writeFileSync(resolve(out,'tab-copy-report.json'),JSON.stringify({pass:true,checks:['Inactive tab copies its own encoded document URL without navigating','Full path preserves Unicode, spaces and punctuation','Tab actions copies active document path','Clipboard failure is visible','Menu remains within narrow/short viewport','Escape dismisses menu'],errors},null,2));console.log('PASS tab URL/path copying, inactive target, failure feedback and narrow menu');
}finally{await browser.close();await app.stop();}
