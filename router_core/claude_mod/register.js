import {makeCoverage,routeAfterClassic} from './eligibility.js';
import {bindings} from './bindings.js';

// Exact-build measured core modules. Ponytail is separately source-verified:
// its Agent/Task tool.call path is a transparent next(e), not a router.
const own='intelligent-agent-router';
const expected=[own,'ponytail','cc-plugin-agents-md','cc-plugin-telemetry','cc-plugin-plugin-authoring'];
const coverage=makeCoverage(own,expected);
let modules=null,started=false,invalid=false,companion=null,registrations=0;
async function bridge($,payload,cwd){
 const r=await $.process.run([bindings.python,`${$.plugin.root}/scripts/router_claude_mod.py`,...bindings.args],
  {cwd,stdin:JSON.stringify(payload),timeoutMs:6000});
 if(r.exitCode!==0||r.isStdoutTruncated||r.isStderrTruncated||r.stdout.length>4096)return null;
 try{return JSON.parse(r.stdout)}catch{return null}
}
export function register(on){
 on('engine.create',async($,e,next)=>{
  if(modules!==null||started){invalid=true;coverage.invalidate()}
  else modules=e.plugins.slice();
  return next(e);
 });
 on('plugin.register',async($,e,next)=>{
  if(started){invalid=true;coverage.invalidate();return next(e)}
  registrations++;
  if(e.name!=='ponytail'||e.tier!=='user'||e.provenance!=='ponytail@ponytail'||e.version!=='5.3.2')invalid=true;
  else companion=e.root;
  const result=await next(e);
  if(result.allow!==true)invalid=true;
  return result;
 });
 on('session.start',async($,e,next)=>{
  if(started){coverage.invalidate();invalid=true;return next(e)}
  started=true;
  if(!invalid&&registrations===1&&companion){
   const proof=await bridge($,{operation:'verify',companion},e.cwd);
   if(!invalid&&proof?.verified===true)coverage.establish(modules);
  }
  $.ui.log(`Worker routing authority: ${coverage.stamp()===null?'unavailable':'verified'}`,{to:'debug'});
  return next(e);
 });
 on('classic.PreToolUse',async($,e,next)=>{
 let original;
 const routed=await routeAfterClassic(e,async(event)=>{original=await next(event);return original},coverage,async(event,batch)=>{
  const cwd=await $.session.cwd();
  const input=batch.updatedInput??Object.fromEntries(Object.entries(event).filter(([k])=>!['tool','tool_use_id','agentId','consent','requestMeta'].includes(k)));
  return bridge($,{cwd,session_id:await $.session.id(),hook_event_name:'PreToolUse',
   tool_name:event.tool,tool_use_id:event.tool_use_id,tool_input:input},cwd);
 });
 if(routed!==original)$.ui.log(`Worker routing: ${routed.updatedInput.model} / ${routed.updatedInput.effort}`);
 return routed;
 });
}
