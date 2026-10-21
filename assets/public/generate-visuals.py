#!/usr/bin/env python3
"""Generate editable HTML diagram originals. Export with diagram-design helpers.
No network, model calls, benchmarks or runtime changes. Python standard library.
"""
from pathlib import Path
from html import escape
OUT = Path(__file__).resolve().parent
CSS = """
:root{--paper:#e8f0ef;--panel:#f7faf9;--ink:#10191d;--muted:#445c60;--line:#647c7c;--accent:#176852;--tint:#d8ebe4;--rule:#abc0bd}
@media(prefers-color-scheme:dark){:root{--paper:#10191d;--panel:#19272b;--ink:#e8f0ef;--muted:#b5cac7;--line:#9db6b2;--accent:#87d8be;--tint:#183c33;--rule:#4b6364}}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink)}main{max-width:100%;min-width:0}.diagram-container{width:100%;overflow-x:auto}svg{width:100%;min-width:960px;display:block;height:auto}.paper{fill:var(--paper)}.panel{fill:var(--panel);stroke:var(--line);stroke-width:1.5}.focal{fill:var(--tint);stroke:var(--accent);stroke-width:2}.ink{fill:var(--ink)}.muted{fill:var(--muted)}.accent{fill:var(--accent)}.title{font:400 40px 'Instrument Serif',Georgia,serif;fill:var(--ink)}.name{font:600 20px 'Geist',system-ui,sans-serif;fill:var(--ink)}.copy{font:400 16px 'Geist',system-ui,sans-serif;fill:var(--muted)}.tag{font:500 12px 'Geist Mono',ui-monospace,monospace;letter-spacing:1.5px;fill:var(--accent)}.small{font:400 14px 'Geist',system-ui,sans-serif;fill:var(--muted)}.arrow{fill:none;stroke:var(--line);stroke-width:2;marker-end:url(#arrow)}.dashed{stroke-dasharray:5 5}.rule{stroke:var(--rule);stroke-width:1}.label{font:500 12px 'Geist Mono',ui-monospace,monospace;fill:var(--muted)}
@media print{.diagram-container{overflow-x:visible}svg{min-width:0}}
"""
def text(x,y,label,cls='copy',anchor=None):
    return f'<text x="{x}" y="{y}" class="{cls}"'+(f' text-anchor="{anchor}"' if anchor else '')+f'>{escape(label)}</text>'
def rect(x,y,w,h,cls='panel',r=8):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" class="{cls}"/>'
def path(d,extra=''):
    return f'<path d="{d}" class="arrow {extra}"/>'
def header(slug,title,desc,w,h):
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" role="img" aria-labelledby="{slug}-title {slug}-desc"><title id="{slug}-title">{escape(title)}</title><desc id="{slug}-desc">{escape(desc)}</desc><defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M 1 1 L 9 5 L 1 9" fill="none" stroke="var(--line)" stroke-width="1.5"/></marker></defs>'+rect(0,0,w,h,'paper',0)
def save(slug,svg):
    OUT.joinpath(slug+'.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+slug.replace('-',' ').title()+'</title><style>'+CSS+('svg{min-width:1280px}@media print{svg{min-width:0}}' if slug=='social-preview' else ('svg{min-width:390px}.tag,.label,.small{font-size:16px}.title{font-size:28px}@media print{svg{min-width:0}}' if slug.endswith('-mobile') else ''))+'</style><main><div class="diagram-container">'+svg+'</svg></div></main></html>')
# Architecture overview: root is a preserved invariant, not part of routing.
s=header('routing-overview','Keep the orchestrator. Route the work.','The main session is preserved while eligible delegated tasks pass through Jev classification and local policy to native Claude Code or Codex workers.',960,680)
s+=text(40,48,'JEV MODEL ROUTER / OVERVIEW','tag')+text(40,100,'Keep the orchestrator. Route the work.','title')
s+=rect(40,136,880,80)+text(64,168,'Main session: unchanged','name')+text(64,196,'Your chosen model and effort stay in control. Routing targets eligible workers only.','copy')
s+=path('M 276 332 H 328')+path('M 592 332 H 644')
s+=path('M 736 396 V 420 Q 736 428 728 428 H 256 Q 248 428 248 436 V 464')
s+=path('M 784 396 V 444 Q 784 452 776 452 H 716 Q 708 452 708 460 V 464')
s+=text(40,256,'DELEGATED ASSIGNMENT','tag')
s+=rect(40,284,236,112)+text(60,320,'Eligible worker task','name')+text(60,352,'Generic and unpinned','copy')+text(60,376,'Consent checked first','small')
s+=rect(328,284,264,112,'focal')+text(348,320,'Jev classifies the task','name')+text(348,352,'Task requirements, not','copy')+text(348,376,'a model-selection command','copy')
s+=rect(644,284,276,112)+text(664,320,'Local policy selects','name')+text(664,352,'Model + supported effort','copy')+text(664,376,'Risk, confidence, catalog','small')
s+=rect(40,464,412,104)+text(60,496,'Claude Code','name')+text(60,524,'Final-classic native adapter','copy')+text(60,548,'Eligible spawn → native worker','small')
s+=rect(500,464,420,104)+text(520,496,'Codex','name')+text(520,524,'Plaintext prepare bridge','copy')+text(520,548,'Single-use reference → native spawn','small')
s+='<line x1="40" y1="600" x2="920" y2="600" class="rule"/>'+text(40,628,'Pins and custom profiles are preserved. Abstention or failure leaves routing unchanged.','small')+text(40,652,'Jev classifies. Local policy decides. The host runs the worker.','small')
save('routing-overview',s)
# Decision flow; no specialized semantic pattern fits this single-request path.
s=header('routing-flow','A route must earn its way in.','Eligibility and consent precede Jev classification; local safety and runtime checks select a model and effort or leave the original request unchanged.',960,848)
s+=text(40,48,'JEV MODEL ROUTER / DECISION FLOW','tag')+text(40,100,'A route must earn its way in.','title')
s+=text(40,140,'Start with a delegated assignment. Keep the main session unchanged.','copy')
s+=path('M 300 304 V 352')+path('M 540 248 H 644')+path('M 300 440 V 488')+path('M 540 544 H 644')+path('M 300 600 V 664')
# Outgoing branch labels are above their strokes with 8px gaps.
for x,y,label in [(312,328,'YES'),(568,234,'NO'),(312,632,'YES'),(568,530,'NO')]:
    s+=rect(x-4,y-14,44,20,'paper',0)+text(x,y,label,'label')
s+='<path d="M 300 192 L 540 248 L 300 304 L 60 248 Z" class="panel"/>'
s+=text(300,244,'Eligible + consented?','name','middle')+text(300,272,'Generic · unpinned · supported','small','middle')
s+=rect(644,200,276,96)+text(664,232,'Preserve the request','name')+text(664,260,'Explicit pins or custom profile?','small')+text(664,280,'Do not classify or override.','small')
s+=rect(120,352,360,88,'focal')+text(144,388,'Jev classifies requirements','name')+text(144,416,'What does this assignment need?','copy')
s+='<path d="M 300 488 L 540 544 L 300 600 L 60 544 Z" class="panel"/>'
s+=text(300,540,'Safe, supported route?','name','middle')+text(300,568,'Risk · confidence · catalog · effort','small','middle')
s+=rect(644,496,276,112)+text(664,528,'Inherit / no rewrite','name')+text(664,556,'Abstain, unavailable or invalid?','small')+text(664,580,'Leave routing unchanged.','small')
s+=rect(120,664,360,80,'focal')+text(144,696,'Apply model + effort','name')+text(144,724,'Native host starts the worker.','copy')
s+='<line x1="40" y1="776" x2="920" y2="776" class="rule"/>'+text(40,804,'Classification failure also inherits. No guessed model IDs or unsupported effort values.','small')+text(40,828,'Permissions, task content and the main-session configuration are not expanded.','small')
save('routing-flow',s)
# Social card uses only explanatory stages, not benchmark or execution claims.
s=header('social-preview','Jev Model Router','Keep the orchestrator and route eligible delegated work through classification and local policy while preserving explicit choices.',1280,640)
s+=text(64,88,'JEV MODEL ROUTER','tag')+text(64,180,'Keep the orchestrator.','title')+text(64,236,'Route the work.','title')
s+=text(64,292,'Task-aware model and effort routing for delegated agents.','copy')
s+=path('M 372 420 H 440')+path('M 764 420 H 832')
s+=rect(64,368,308,104)+text(88,408,'Delegate a task','name')+text(88,440,'Generic, unpinned assignment','copy')
s+=rect(440,368,324,104,'focal')+text(464,408,'Classify with Jev','name')+text(464,440,'Requirements → local policy','copy')
s+=rect(832,368,384,104)+text(856,408,'Route a native worker','name')+text(856,440,'Verified model + supported effort','copy')
s+='<line x1="64" y1="520" x2="1216" y2="520" class="rule"/>'+text(64,560,'MAIN SESSION PRESERVED','tag')+text(620,560,'Explicit choices win. Failures inherit.','copy')
save('social-preview',s)
# Compact responsive artwork: every label is at least 16 viewBox units,
# retaining >14 CSS px inside a typical 358px-wide phone README image.
s=header('routing-overview-mobile','Keep the orchestrator. Route the work.','Eligible delegated tasks are classified by Jev and routed by local policy; the main session, explicit pins and custom profiles are preserved.',390,1040)
s+=text(24,40,'JEV MODEL ROUTER','tag')+text(24,84,'Route the work.','title')
s+=path('M 195 332 V 376')+path('M 195 464 V 508')+path('M 195 612 V 656')
s+=rect(24,112,342,88)+text(44,144,'Main session: unchanged','name')+text(44,172,'Keep your model and effort.','copy')
s+=rect(24,244,342,88)+text(44,276,'Eligible delegated task','name')+text(44,304,'Generic · unpinned · consented','copy')
s+=rect(24,376,342,88,'focal')+text(44,408,'Jev classifies requirements','name')+text(44,436,'Classification, not model choice','copy')
s+=rect(24,508,342,104)+text(44,540,'Local policy selects','name')+text(44,568,'Model + supported effort','copy')+text(44,592,'Risk · confidence · catalog','copy')
s+=rect(24,656,342,216)+text(44,688,'Native worker hosts','name')+text(44,724,'Claude Code','name')+text(44,752,'Final-classic native adapter','copy')+text(44,792,'Codex','name')+text(44,820,'Plaintext prepare bridge','copy')+text(44,848,'Single-use ref → native spawn','copy')
s+='<line x1="24" y1="912" x2="366" y2="912" class="rule"/>'+text(24,948,'Pins and custom profiles are preserved.','small')+text(24,976,'Abstention or failure: no rewrite.','small')+text(24,1004,'The host executes the worker.','small')
save('routing-overview-mobile',s)
s=header('routing-flow-mobile','A route must earn its way in.','Eligibility and consent precede classification and local policy; rejected checks and failures preserve the request instead of guessing a route.',390,996)
s+=text(24,40,'JEV / DECISION FLOW','tag')+text(24,84,'A route must earn its way in.','title')+text(24,124,'Start with a delegated assignment.','copy')
s+=path('M 195 320 V 368')+path('M 195 480 V 528')+path('M 195 672 V 720')
s+=rect(24,176,342,144)+text(44,208,'1. Eligibility + consent','name')+text(44,236,'Generic, unpinned, valid boundary?','copy')+text(44,264,'Pins / custom profiles: preserve.','copy')+text(44,296,'Not eligible? Do not classify.','copy')
s+=rect(24,368,342,112,'focal')+text(44,400,'2. Jev classifies the task','name')+text(44,428,'Extract task requirements.','copy')+text(44,456,'Abstention / failure: inherit.','copy')
s+=rect(24,528,342,144)+text(44,560,'3. Local policy checks','name')+text(44,588,'Risk · confidence · catalog','copy')+text(44,616,'Verified model + supported effort?','copy')+text(44,648,'No safe route? Leave unchanged.','copy')
s+=rect(24,720,342,88,'focal')+text(44,752,'4. Apply model + effort','name')+text(44,780,'Native host starts the worker.','copy')
s+='<line x1="24" y1="848" x2="366" y2="848" class="rule"/>'+text(24,884,'Main-session settings stay unchanged.','small')+text(24,912,'Explicit choices win. Failures inherit.','small')+text(24,940,'No guessed model IDs or effort values.','small')+text(24,968,'No expanded permissions.','small')
save('routing-flow-mobile',s)
print('Generated 5 editable HTML originals')
