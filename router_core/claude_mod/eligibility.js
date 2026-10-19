// Pure final-batch eligibility/merge. Authority is established by register.js.
const own=(o,k)=>Object.prototype.hasOwnProperty.call(o,k);
const pins=['model','effort','reasoning_effort'];
function plain(o){ return o!==null && typeof o==='object' && !Array.isArray(o) && [Object.prototype,null].includes(Object.getPrototypeOf(o)); }
function safeData(o,depth=0){
 if(depth>20)return false;
 if(o===null || ['string','boolean'].includes(typeof o))return true;
 if(typeof o==='number')return Number.isFinite(o);
 if(Array.isArray(o))return o.every(v=>safeData(v,depth+1));
 return plain(o) && Object.keys(o).every(k=>!['__proto__','constructor','prototype'].includes(k) && safeData(o[k],depth+1));
}
export function makeCoverage(ownName,expected){
 let good=false,seen=false,revision=0;
 const configured=typeof ownName==='string' && Array.isArray(expected) && expected.length>=2 && new Set(expected).size===expected.length && expected.includes(ownName) && expected.every(n=>typeof n==='string'&&n.length>0);
 return {
  establish(names){revision++;good=false;if(seen)return false;seen=true;
   good=configured && Array.isArray(names) && names.length===expected.length && names.every((n,i)=>n===expected[i]);return good;},
  invalidate(){revision++;good=false;},
  stamp(){return good?revision:null;},
  valid(stamp){return good && stamp!==null && stamp===revision;}
 };
}
export function eligible(event,batch){
 if(!plain(event)||!['Agent','Task'].includes(event.tool)||typeof event.prompt!=='string'||!event.prompt.trim())return false;
 if(!plain(batch)||!safeData(batch)||JSON.stringify(batch).length>200000)return false;
 if(Object.keys(batch).some(k=>!['allow','ask','deny','updatedInput','additionalContext'].includes(k)))return false;
 const decisions=['allow','ask','deny'].filter(k=>own(batch,k));
 if(decisions.length>1 || (own(batch,'allow') && batch.allow!==true))return false;
 if(own(batch,'ask')||own(batch,'deny'))return false; // no provider work for blocked/prompted calls
 if(own(batch,'additionalContext')&&(!Array.isArray(batch.additionalContext)||batch.additionalContext.some(s=>typeof s!=='string')))return false;
 if(own(batch,'updatedInput')&&!plain(batch.updatedInput))return false;
 const resultInput=own(batch,'updatedInput')?batch.updatedInput:event;
 if(pins.some(k=>own(event,k)||own(resultInput,k)))return false;
 if([event,resultInput].some(o=>own(o,'subagent_type')&&o.subagent_type!=='general-purpose'))return false;
 if([event,resultInput].some(o=>own(o,'resume')||o.fork===true))return false;
 if(own(batch,'updatedInput') && (typeof resultInput.prompt!=='string'||!resultInput.prompt.trim()))return false;
 return true;
}
export async function routeAfterClassic(event,next,coverage,provider){
 const stamp=coverage.stamp();
 const batch=await next(event); // Exactly one downstream call; its rejection propagates.
 try{
  if(!coverage.valid(stamp)||!eligible(event,batch))return batch;
  const proposal=await provider(event,batch);
  if(!coverage.valid(stamp)||!plain(proposal)||Object.keys(proposal).some(k=>!['model','effort'].includes(k))||typeof proposal.model!=='string'||!proposal.model|| (own(proposal,'effort')&&!['low','medium','high','xhigh','max'].includes(proposal.effort)))return batch;
  const input=own(batch,'updatedInput')?batch.updatedInput:Object.fromEntries(Object.entries(event).filter(([k])=>!['tool','tool_use_id','agentId','consent','requestMeta'].includes(k)));
  return {...batch,updatedInput:{...input,...proposal}};
 }catch{return batch;} // A provider/validation failure never re-enters next or changes permission output.
}
