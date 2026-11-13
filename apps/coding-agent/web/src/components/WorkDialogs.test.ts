import { afterEach, expect, it, vi } from 'vitest';
import { readWorkRows } from './WorkDialogs';
afterEach(()=>vi.unstubAllGlobals());
it('reads later resource and native-run pages before an owner decision',async()=>{
 const fetch=vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({items:[{id:'deleted',state:'deleted'}],nextCursor:'older/page'}))).mockResolvedValueOnce(new Response(JSON.stringify({items:[{id:'present',state:'present'}],nextCursor:''})));
 vi.stubGlobal('fetch',fetch);
 expect(await readWorkRows('/api/sessions/s/resources')).toEqual([{id:'deleted',state:'deleted'},{id:'present',state:'present'}]);
 expect(fetch.mock.calls[1][0]).toContain('cursor=older%2Fpage');
});
it('fails closed when a later page is missing, even when the optional feature fallback is allowed',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValueOnce(new Response(JSON.stringify({items:[{id:'resource'}],nextCursor:'more'}))).mockResolvedValueOnce(new Response('',{status:404})));
 await expect(readWorkRows('/api/sessions/s/resources',true)).rejects.toThrow('all saved resources');
});
it('refuses a repeating cursor instead of silently showing an incomplete decision set',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockImplementation(()=>Promise.resolve(new Response(JSON.stringify({items:[],nextCursor:'same'})))));
 await expect(readWorkRows('/api/sessions/s/operations?active=true')).rejects.toThrow('did not advance');
});
