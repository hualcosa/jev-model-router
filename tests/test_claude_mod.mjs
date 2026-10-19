import test from 'node:test';
import assert from 'node:assert/strict';
import {makeCoverage,eligible,routeAfterClassic} from '../router_core/claude_mod/eligibility.js';
const event={tool:'Agent',tool_use_id:'id',prompt:'Synthetic task',description:'Synthetic',subagent_type:'general-purpose'};
function authority(){const c=makeCoverage('router',['router','witness']);c.establish(['router','witness']);return c}
test('routing preserves the final batch and changes only model/effort',async()=>{
 const batch={additionalContext:['keep'],updatedInput:{prompt:'Revised task',description:'keep'}};
 const out=await routeAfterClassic(event,async()=>batch,authority(),async()=>({model:'haiku',effort:'medium'}));
 assert.deepEqual(out,{...batch,updatedInput:{...batch.updatedInput,model:'haiku',effort:'medium'}});
 assert.equal(batch.updatedInput.model,undefined);
});
for(const batch of [{ask:'ask'},{deny:'deny'},{updatedInput:{prompt:'task',model:'sonnet'}},{updatedInput:{prompt:'task',effort:'high'}},{unknown:true},null]){
 test(`unsafe batch remains unchanged ${JSON.stringify(batch)}`,async()=>{
  let calls=0;assert.equal(await routeAfterClassic(event,async()=>batch,authority(),async()=>{calls++;return {model:'haiku'}}),batch);assert.equal(calls,0);
 });
}
for(const patch of [{model:null},{effort:'medium'},{subagent_type:'custom'},{resume:'id'}])test('pins and custom profiles abstain '+JSON.stringify(patch),()=>assert.equal(eligible({...event,...patch},{}),false));
test('invalidation during provider preserves outcome',async()=>{
 const c=authority(),batch={}; assert.equal(await routeAfterClassic(event,async()=>batch,c,async()=>{c.invalidate();return {model:'haiku'}}),batch);
});
test('downstream failure calls next exactly once',async()=>{
 let calls=0;await assert.rejects(routeAfterClassic(event,async()=>{calls++;throw Error('fixture')},authority(),async()=>({model:'haiku'})));assert.equal(calls,1);
});
test('own-only and reload cannot grant authority',()=>{
 const c=makeCoverage('router',['router','witness']);assert.equal(c.establish(['router']),false);assert.equal(c.establish(['router','witness']),false);assert.equal(c.stamp(),null);
});
