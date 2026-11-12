import {describe,it,expect} from 'vitest';
import {acceptsAgentQuery,type SqlQuery} from './query';
import {reduce,emptySession,type AgentEvent} from './events';
const saved={id:'id',name:'Query',text:'SELECT 1',warehouseId:'w',catalog:'c',schema:'s'} as SqlQuery;
const local={text:'SELECT 1',name:'Query',warehouseId:'w',catalog:'c',schema:'s'};
describe('agent query synchronization',()=>{
 it('accepts remote changes only while every local input still matches the captured snapshot',()=>{
  expect(acceptsAgentQuery(local,saved)).toBe(true);
  for(const key of Object.keys(local) as (keyof typeof local)[])expect(acceptsAgentQuery({...local,[key]:'human change'},saved)).toBe(false);
 });
 it('replays the latest authoritative change once and keeps other query identities separate',()=>{
  const event={type:'sql.changed',sessionId:'session',seq:4,draftId:'a',version:2,runId:'run'} as AgentEvent;
  const s=reduce(emptySession(),event);
  expect(s.sqlChanges?.a).toEqual({seq:4,version:2,runId:'run'});
  expect(reduce(s,event)).toBe(s);
  expect(reduce(s,{...event,seq:3,runId:'older'})).toBe(s);
  const other=reduce(s,{...event,seq:5,draftId:'b'});
  expect(other.sqlChanges?.a).toEqual(s.sqlChanges?.a);
  expect(other.sqlChanges?.b.runId).toBe('run');
 });
});
