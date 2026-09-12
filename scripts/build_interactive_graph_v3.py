from __future__ import annotations

import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

PROJECT = Path.home() / "concept-language"
DATA_ROOT = PROJECT / "data" / "external" / "UD_Persian-PerDT"
INPUT_FILE = DATA_ROOT / "fa_perdt-ud-dev.conllu"
OUTPUT_FILE = PROJECT / "results" / "graphs" / "perdt_interactive_v3.html"
PUBLIC_FILE = PROJECT / "public" / "index.html"
ID_RE = re.compile(r"^\d+(?:\.\d+)?$")


def read_conllu(path: Path):
    sentences, current = [], []
    with path.open("r", encoding="utf-8-sig") as f:
        for raw in f:
            line = raw.rstrip("\r\n")
            if not line:
                if current:
                    sentences.append(current)
                    current = []
                continue
            if line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != 10 or not ID_RE.match(parts[0]):
                continue
            try:
                token_id = int(float(parts[0]))
                head_id = int(parts[6]) if parts[6].isdigit() else 0
            except ValueError:
                continue
            current.append({
                "id": token_id, "form": parts[1],
                "lemma": parts[2] if parts[2] != "_" else parts[1],
                "upos": parts[3], "feats": parts[5],
                "head": head_id, "deprel": parts[7],
            })
    if current:
        sentences.append(current)
    return sentences


def parse_feats(text):
    if not text or text == "_":
        return {}
    out = {}
    for item in text.split("|"):
        if "=" in item:
            k, v = item.split("=", 1)
            out[k] = v
    return out


def analyze(sentences):
    lemma_stats = defaultdict(lambda: {
        "count": 0, "forms": Counter(), "upos": Counter(),
        "in_rel": Counter(), "out_rel": Counter(), "examples": []
    })
    edge_counts = Counter()
    edge_examples = defaultdict(list)

    for sent in sentences:
        by_id = {t["id"]: t for t in sent}
        sentence_text = " ".join(t["form"] for t in sent)
        for tok in sent:
            lemma = tok["lemma"]
            s = lemma_stats[lemma]
            s["count"] += 1
            s["forms"][tok["form"]] += 1
            s["upos"][tok["upos"]] += 1

            head = by_id.get(tok["head"])
            if head is None or tok["head"] == 0:
                continue

            src, dst, rel = head["lemma"], lemma, tok["deprel"]
            key = (src, dst, rel)
            edge_counts[key] += 1
            s["in_rel"][rel] += 1
            lemma_stats[src]["out_rel"][rel] += 1
            if len(edge_examples[key]) < 3:
                edge_examples[key].append(sentence_text)
            if len(s["examples"]) < 5:
                s["examples"].append({
                    "sentence": sentence_text,
                    "form": tok["form"],
                    "head": src,
                    "relation": rel,
                    "features": parse_feats(tok["feats"]),
                })

    rows = []
    for lemma, s in lemma_stats.items():
        rows.append({
            "lemma": lemma,
            "count": s["count"],
            "forms": s["forms"].most_common(20),
            "upos": s["upos"].most_common(10),
            "in_rel": s["in_rel"].most_common(20),
            "out_rel": s["out_rel"].most_common(20),
            "examples": s["examples"],
        })
    rows.sort(key=lambda x: (-x["count"], x["lemma"]))

    edges = []
    for (src, dst, rel), count in edge_counts.items():
        edges.append({
            "source": src, "target": dst, "relation": rel,
            "count": count, "examples": edge_examples[(src, dst, rel)]
        })
    return rows, edges


def build_html(rows, edges, sentence_count):
    payload = {"sentences": sentence_count, "lemmas": rows[:6000], "edges": edges}
    payload_json = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    html_doc = r'''<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Type" content="text/html; charset=utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Concept Language Lab — V3</title>
<style>
*{box-sizing:border-box}body{margin:0;font-family:"Segoe UI",Tahoma,Arial,sans-serif;background:#f5f7fb;color:#1f2937}
header{background:#111827;color:#fff;padding:16px 20px}header h1{margin:0 0 4px;font-size:20px}header div{color:#cbd5e1;font-size:12px}
main{display:grid;grid-template-columns:380px 1fr;min-height:calc(100vh - 75px)}
aside{background:#fff;border-left:1px solid #dbe1e8;padding:16px;overflow:auto}section{padding:16px}
input,select,button{width:100%;padding:10px 12px;margin:4px 0;border:1px solid #cbd5e1;border-radius:8px;font-size:14px}
button{background:#2563eb;color:#fff;border:0;cursor:pointer}button.secondary{background:#64748b}
.card{background:#fff;border:1px solid #dbe1e8;border-radius:10px;padding:12px;margin-top:10px}.match{cursor:pointer}.match:hover{background:#eff6ff}
.small{font-size:12px;color:#64748b}.pill{display:inline-block;background:#eef2ff;color:#3730a3;border-radius:999px;padding:3px 7px;margin:2px;font-size:11px}
#canvasWrap{background:#fff;border:1px solid #dbe1e8;border-radius:10px;overflow:hidden}#networkSvg{width:100%;height:72vh;min-height:620px;display:block}
.edge-label{font-size:11px;fill:#475569}.node{cursor:pointer}.legend{display:flex;gap:10px;flex-wrap:wrap;font-size:12px}.dot{width:10px;height:10px;border-radius:50%;display:inline-block}
h3,h4{margin:6px 0 8px}ul{padding-right:20px}
</style>
</head>
<body>
<header><h1>Concept Language Lab — Interactive Graph V3</h1><div>UTF-8 · lemma/form · dependency relations · sentence evidence</div></header>
<main>
<aside>
<h3>جست‌وجوی واژه</h3>
<input id="query" placeholder="واژه یا lemma..." oninput="renderMatches()">
<select id="upos" onchange="renderMatches()">
<option value="">همهٔ نقش‌ها</option><option value="NOUN">NOUN</option><option value="VERB">VERB</option><option value="ADJ">ADJ</option><option value="ADV">ADV</option><option value="PRON">PRON</option><option value="PROPN">PROPN</option><option value="DET">DET</option><option value="ADP">ADP</option><option value="NUM">NUM</option><option value="CONJ">CONJ</option>
</select>
<button onclick="showSelectedGraph()">نمایش شبکهٔ انتخاب‌شده</button>
<button class="secondary" onclick="showStats()">آمار پیکره</button>
<div id="matches" class="card"></div><div id="details" class="card"></div>
</aside>
<section><div id="canvasWrap"><svg id="networkSvg" viewBox="0 0 1200 760" xmlns="http://www.w3.org/2000/svg"></svg></div></section>
</main>
<script>
const DATA = PAYLOAD_PLACEHOLDER;
let selectedLemma = DATA.lemmas.length ? DATA.lemmas[0].lemma : "";
function esc(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));}
function norm(s){return String(s||"").trim().toLowerCase();}
function renderMatches(){
 const q=norm(document.getElementById("query").value), u=document.getElementById("upos").value, box=document.getElementById("matches");
 const hits=DATA.lemmas.filter(r=>(!u||r.upos.some(x=>x[0]===u))&&(!q||norm(r.lemma).includes(q)||r.forms.some(x=>norm(x[0]).includes(q)))).slice(0,50);
 if(!hits.length){box.innerHTML="<div>نتیجه‌ای پیدا نشد.</div>";return;}
 box.innerHTML="<b>نتایج</b>"+hits.map(r=>'<div class="card match" onclick="selectLemma('+JSON.stringify(r.lemma)+')"><b>'+esc(r.lemma)+'</b><div class="small">count='+r.count+' · forms: '+r.forms.slice(0,4).map(x=>esc(x[0])).join("، ")+'</div></div>').join("");
}
function selectLemma(lemma){
 selectedLemma=lemma;const row=DATA.lemmas.find(x=>x.lemma===lemma);if(!row)return;
 const forms=row.forms.map(x=>'<li>'+esc(x[0])+' <span class="small">('+x[1]+')</span></li>').join("");
 const incoming=row.in_rel.map(x=>'<li><span class="pill">'+esc(x[0])+'</span> '+x[1]+'</li>').join("");
 const outgoing=row.out_rel.map(x=>'<li><span class="pill">'+esc(x[0])+'</span> '+x[1]+'</li>').join("");
 const examples=row.examples.map(e=>'<li><div>'+esc(e.sentence)+'</div><div class="small">'+esc(e.form)+' · '+esc(e.relation)+' · head='+esc(e.head)+'</div></li>').join("");
 document.getElementById("details").innerHTML='<h3>'+esc(row.lemma)+'</h3><div><b>رخداد:</b> '+row.count+'</div><div><b>UPOS:</b> '+row.upos.map(x=>esc(x[0])+' ('+x[1]+')').join("، ")+'</div><h4>شکل‌های ثبت‌شده</h4><ul>'+forms+'</ul><h4>روابط ورودی</h4><ul>'+(incoming||'<li>—</li>')+'</ul><h4>روابط خروجی</h4><ul>'+(outgoing||'<li>—</li>')+'</ul><h4>شاهدهای جمله‌ای</h4><ul>'+(examples||'<li>—</li>')+'</ul>';
 showSelectedGraph();
}
function neighborhood(seed){
 const adj={};DATA.edges.forEach(e=>{(adj[e.source]??=[]).push(e.target);(adj[e.target]??=[]).push(e.source)});
 const selected=new Set([seed]),frontier=new Set([seed]);
 for(let d=0;d<1;d++){const next=new Set();frontier.forEach(n=>(adj[n]||[]).forEach(x=>next.add(x)));next.forEach(x=>selected.add(x));}
 return Array.from(selected).slice(0,70);
}
function showSelectedGraph(){drawNetwork(selectedLemma,neighborhood(selectedLemma));}
function drawNetwork(seed,nodes){
 const svg=document.getElementById("networkSvg");while(svg.firstChild)svg.removeChild(svg.firstChild);
 const W=1200,H=760,cx=W/2,cy=H/2,positions={};positions[seed]=[cx,cy];
 const others=nodes.filter(n=>n!==seed),rx=420,ry=280;others.forEach((n,i)=>{const a=2*Math.PI*i/Math.max(1,others.length)-Math.PI/2;positions[n]=[cx+rx*Math.cos(a),cy+ry*Math.sin(a)]});
 function add(tag,attrs,text){const n=document.createElementNS("http://www.w3.org/2000/svg",tag);Object.keys(attrs).forEach(k=>n.setAttribute(k,attrs[k]));if(text!=null)n.textContent=text;svg.appendChild(n);return n}
 add("rect",{x:0,y:0,width:W,height:H,fill:"#fff"});
 const defs=document.createElementNS("http://www.w3.org/2000/svg","defs"),marker=document.createElementNS("http://www.w3.org/2000/svg","marker"),path=document.createElementNS("http://www.w3.org/2000/svg","path");
 marker.setAttribute("id","arrow");marker.setAttribute("markerWidth","10");marker.setAttribute("markerHeight","10");marker.setAttribute("refX","8");marker.setAttribute("refY","3");marker.setAttribute("orient","auto");path.setAttribute("d","M0,0 L0,6 L9,3 z");path.setAttribute("fill","#94a3b8");marker.appendChild(path);defs.appendChild(marker);svg.appendChild(defs);
 DATA.edges.forEach(e=>{if(!positions[e.source]||!positions[e.target])return;const p1=positions[e.source],p2=positions[e.target];add("line",{x1:p1[0],y1:p1[1],x2:p2[0],y2:p2[1],stroke:"#cbd5e1","stroke-width":1.2,"marker-end":"url(#arrow)"});add("text",{x:(p1[0]+p2[0])/2,y:(p1[1]+p2[1])/2,"text-anchor":"middle",class:"edge-label"},e.relation)});
 nodes.forEach(n=>{if(!positions[n])return;const p=positions[n],sel=n===seed,g=document.createElementNS("http://www.w3.org/2000/svg","g");g.setAttribute("class","node");g.addEventListener("click",()=>selectLemma(n));const c=document.createElementNS("http://www.w3.org/2000/svg","circle");c.setAttribute("cx",p[0]);c.setAttribute("cy",p[1]);c.setAttribute("r",sel?27:17);c.setAttribute("fill",sel?"#fb7185":"#93c5fd");c.setAttribute("stroke","#475569");g.appendChild(c);const t=document.createElementNS("http://www.w3.org/2000/svg","text");t.setAttribute("x",p[0]);t.setAttribute("y",p[1]-24);t.setAttribute("text-anchor","middle");t.setAttribute("font-size",sel?18:14);t.textContent=n;g.appendChild(t);svg.appendChild(g)});
}
function showStats(){const total=DATA.lemmas.reduce((a,b)=>a+b.count,0);document.getElementById("details").innerHTML='<h3>آمار پیکره</h3><div>جمله‌ها: <b>'+DATA.sentences.toLocaleString()+'</b></div><div>lemmaهای یکتا: <b>'+DATA.lemmas.length.toLocaleString()+'</b></div><div>رخدادهای واژگانی: <b>'+total.toLocaleString()+'</b></div><div>یال‌های رابطه‌ای: <b>'+DATA.edges.length.toLocaleString()+'</b></div>';}
renderMatches();if(selectedLemma)selectLemma(selectedLemma);
</script>
</body></html>
'''
    html_doc = html_doc.replace("PAYLOAD_PLACEHOLDER", payload_json)
    OUTPUT_FILE.write_text(html_doc, encoding="utf-8")
    PUBLIC_FILE.write_text(html_doc, encoding="utf-8")
    return len(rows), len(edges)


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Input corpus not found: {INPUT_FILE}")
    sentences = read_conllu(INPUT_FILE)
    rows, edges = analyze(sentences)
    n_lemmas, n_edges = build_html(rows, edges, len(sentences))
    print(f"Sentences: {len(sentences):,}")
    print(f"Unique lemmas: {n_lemmas:,}")
    print(f"Relation edges: {n_edges:,}")
    print(f"Local HTML: {OUTPUT_FILE}")
    print(f"Firebase public/index.html: {PUBLIC_FILE}")


if __name__ == "__main__":
    main()
