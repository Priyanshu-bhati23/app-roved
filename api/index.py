"""Vercel entry point: an upload page in front of the App-roved API.

Vercel limits a request body to about 4.5 MB, so real-world IPAs usually need the CLI
or the Docker image. The "Try a sample build" button scans a synthetic IPA generated on
the server (the same builder the test suite uses), so visitors can see a full report.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("APPROVED_MAX_UPLOAD_MB", "4")

from fastapi.responses import HTMLResponse  # noqa: E402

from approved import ipa, llm, rag  # noqa: E402
from approved.api import _settings, app  # noqa: E402
from approved.catalog import Report  # noqa: E402
from approved.engine import analyze  # noqa: E402
from tests.builders import GOOD_INFO, build_ipa, build_macho  # noqa: E402


def _sample_ipa() -> bytes:
    info = dict(GOOD_INFO, NSAppTransportSecurity={"NSAllowsArbitraryLoads": True}, NSCameraUsageDescription="")
    binary = build_macho(
        sdk=(18, 2, 0),
        symbols=("_stat", "_OBJC_CLASS_$_NSUserDefaults", "_OBJC_CLASS_$_CLLocationManager"),
        entitlements={"get-task-allow": True},
    )
    return build_ipa(info=info, binary=binary)


@app.post("/v1/demo-scan", response_model=Report, include_in_schema=False)
def demo_scan() -> Report:
    return rag.explain_report(analyze(ipa.load(_sample_ipa()), _settings()), llm.from_env())


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def page() -> str:
    return PAGE


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>App-roved</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap">
<style>
:root{--bg:#07080f;--panel:#0f1222;--line:#232845;--ink:#e9ecf7;--muted:#9aa1bd;--faint:#5d6485;--acc:#5fd4ff;--block:#ff5d73;--warn:#ffb547;--info:#8f9bd6;color-scheme:dark}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 "Inter Tight",system-ui,sans-serif}
main{max-width:900px;margin:0 auto;padding:40px max(16px,env(safe-area-inset-left)) 60px}
.eye{font:500 12px/1 "JetBrains Mono",monospace;letter-spacing:.12em;text-transform:uppercase;color:var(--acc)}
h1{font-size:clamp(30px,5vw,48px);line-height:1.04;margin:10px 0;letter-spacing:-.02em}
.lede{color:var(--muted);max-width:64ch;margin:0 0 24px}
.drop{display:grid;place-items:center;gap:6px;text-align:center;border:1.5px dashed var(--line);border-radius:16px;padding:30px 16px;background:var(--panel);cursor:pointer}
.drop:hover,.drop.over{border-color:var(--acc)}.drop input{display:none}.drop b{font-size:17px}.drop span{color:var(--faint);font-size:13px}
.row{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:14px 0 30px}
button{background:var(--acc);color:#03141c;border:0;border-radius:12px;padding:12px 18px;font:600 15px "Inter Tight",sans-serif;cursor:pointer}
button:disabled{opacity:.5;cursor:wait}.muted{color:var(--faint);font-size:13px}
.legend{display:flex;gap:14px;flex-wrap:wrap;font:12px "JetBrains Mono",monospace;color:var(--muted);margin-bottom:18px}
.summary{display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px 20px;margin-bottom:14px}
.verdict{font:700 22px "Inter Tight";text-transform:uppercase;letter-spacing:.02em}
.v-blocked{color:var(--block)}.v-needs_review{color:var(--warn)}.v-clear{color:#4fe3a1}
.f{background:var(--panel);border:1px solid var(--line);border-left:4px solid var(--sev);border-radius:12px;padding:16px 18px;margin-bottom:12px}
.f-head{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:6px}
.tag{font:500 11px "JetBrains Mono",monospace;padding:4px 8px;border-radius:6px;border:1px solid var(--line);color:var(--muted)}
.tag.sev{color:var(--sev);border-color:var(--sev)}
.f h3{margin:0 0 6px;font-size:17px}.f p{margin:0 0 8px;color:var(--ink)}
.ev{font:12px/1.5 "JetBrains Mono",monospace;color:var(--muted);background:#06070d;border-radius:8px;padding:8px 10px;overflow-x:auto;white-space:pre-wrap;word-break:break-word}
.f a{color:var(--acc);font-size:13px}.cite{color:var(--acc);font-family:"JetBrains Mono",monospace;font-size:12px}
.err{color:var(--block)}footer{color:var(--faint);font:12px "JetBrains Mono",monospace;margin-top:30px}footer a{color:var(--muted)}
</style></head><body><main>
<div class="eye">iOS compliance · static analysis · RAG</div>
<h1>Will this build pass App Store review?</h1>
<p class="lede">Upload an .ipa. App-roved reads the Mach-O binary and Info.plist directly, runs 19 deterministic checks, and labels every finding by how we know it is a rule. An LLM explains each finding, and only from passages it actually retrieved.</p>
<label class="drop" id="drop"><input id="file" type="file" accept=".ipa"><b>Choose an .ipa or drop it here</b><span>Up to 4 MB on this demo. Larger builds: use the CLI or Docker image from GitHub.</span></label>
<div class="row"><button id="sample" type="button">Try a sample build</button><span class="muted">A synthetic IPA with six planted problems. Explanations take 10–20 seconds.</span></div>
<div class="legend"><span>OFFICIAL · stated in Apple's docs</span><span>COMMUNITY_HEURISTIC · widely reported</span><span>NOT_PUBLICLY_VERIFIABLE · never blocks</span></div>
<div id="out"></div>
<footer><a href="https://github.com/Priyanshu-bhati23/app-roved" target="_blank" rel="noopener">source on GitHub</a> · <a href="/docs">API docs</a></footer>
</main><script>
const out=document.getElementById("out"),file=document.getElementById("file"),drop=document.getElementById("drop"),sample=document.getElementById("sample");
const SEV={blocker:"var(--block)",warning:"var(--warn)",info:"var(--info)"};
const esc=s=>String(s).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
async function scan(req,label){sample.disabled=true;out.innerHTML='<p class="muted">Scanning '+esc(label)+'…</p>';
try{const r=await fetch(req.url,req.opts);const d=await r.json();if(!r.ok)throw new Error(typeof d.detail==="string"?d.detail:"Scan failed ("+r.status+")");render(d)}
catch(e){out.innerHTML='<p class="err">'+esc(e.message)+'</p>'}sample.disabled=false}
function render(d){const c=d.counts;out.innerHTML='<div class="summary"><div><div class="muted">'+esc(d.app_name)+' '+esc(d.version||"")+' · '+esc(d.bundle_id||"")+' · SDK '+esc(d.sdk||"?")+'</div><div class="verdict v-'+d.verdict+'">'+d.verdict.replace("_"," ")+'</div></div><div class="muted">'+c.blocker+' blocker · '+c.warning+' warning · '+c.info+' info</div></div>'+
(d.findings.length?d.findings.map(f=>{const s=f.signal,x=f.explanation;return '<div class="f" style="--sev:'+SEV[s.severity]+'"><div class="f-head"><span class="tag sev">'+s.severity+'</span><span class="tag">'+s.id+'</span><span class="tag">'+s.provenance+'</span><span class="tag">'+s.detection+'</span></div><h3>'+esc(s.title)+'</h3>'+
(x?'<p>'+esc(x.text).replace(/[\\[\\u3010](kb:[a-z0-9-]+#\\d+)[\\]\\u3011]/g,'<span class="cite">[$1]</span>')+'</p>':'<p>'+esc(s.summary)+'</p>')+'<div class="ev">'+esc(JSON.stringify(f.evidence))+'</div>'+(s.source?'<p style="margin-top:8px"><a href="'+esc(s.source)+'" target="_blank" rel="noopener">Apple source ↗</a></p>':'')+'</div>'}).join(""):'<p>No findings: nothing in the catalog matched this build.</p>')}
sample.onclick=()=>scan({url:"/v1/demo-scan",opts:{method:"POST"}},"the sample build");
function upload(f){if(!f)return;if(f.size>4*1024*1024){out.innerHTML='<p class="err">'+esc(f.name)+' is '+(f.size/1048576).toFixed(1)+' MB. This demo accepts up to 4 MB; run the CLI from GitHub for larger builds.</p>';return}
const fd=new FormData();fd.append("file",f);scan({url:"/v1/scans",opts:{method:"POST",body:fd}},f.name)}
file.onchange=()=>upload(file.files[0]);
drop.addEventListener("dragover",e=>{e.preventDefault();drop.classList.add("over")});drop.addEventListener("dragleave",()=>drop.classList.remove("over"));
drop.addEventListener("drop",e=>{e.preventDefault();drop.classList.remove("over");upload(e.dataTransfer.files[0])});
</script></body></html>"""
