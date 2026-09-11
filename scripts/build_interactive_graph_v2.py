from __future__ import annotations

import html
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from pyvis.network import Network

PROJECT = Path(r"C:\Users\asus\concept-language")
DATA_ROOT = PROJECT / "data" / "external" / "UD_Persian-PerDT"
INPUT_FILE = DATA_ROOT / "fa_perdt-ud-dev.conllu"
OUTPUT_FILE = PROJECT / "results" / "graphs" / "perdt_interactive_v2.html"

TOKEN_ID_RE = re.compile(r"^\d+$")


def read_conllu(path: Path):
    sentences = []
    current = []
    with path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line:
                if current:
                    sentences.append(current)
                    current = []
                continue
            if line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) != 10 or not TOKEN_ID_RE.match(parts[0]):
                continue
            current.append({
                "id": int(parts[0]),
                "form": parts[1],
                "lemma": parts[2] if parts[2] != "_" else parts[1],
                "upos": parts[3],
                "feats": parts[5],
                "head": int(parts[6]) if parts[6].isdigit() else 0,
                "deprel": parts[7],
            })
    if current:
        sentences.append(current)
    return sentences


def build_indexes(sentences):
    lemma_info = defaultdict(lambda: {
        "forms": Counter(),
        "upos": Counter(),
        "relations": Counter(),
    })
    edges = Counter()
    form_to_lemmas = defaultdict(Counter)

    for sent in sentences:
        by_id = {t["id"]: t for t in sent}
        for tok in sent:
            lemma = tok["lemma"]
            form = tok["form"]
            lemma_info[lemma]["forms"][form] += 1
            lemma_info[lemma]["upos"][tok["upos"]] += 1
            form_to_lemmas[form][lemma] += 1

            head = by_id.get(tok["head"])
            if head is not None and tok["head"] != 0:
                h = head["lemma"]
                rel = tok["deprel"]
                edges[(h, lemma, rel)] += 1
                lemma_info[h]["relations"][f"out:{rel}"] += 1
                lemma_info[lemma]["relations"][f"in:{rel}"] += 1

    rows = []
    for lemma, info in lemma_info.items():
        rows.append({
            "lemma": lemma,
            "count": sum(info["forms"].values()),
            "upos": info["upos"].most_common(),
            "forms": info["forms"].most_common(12),
            "relations": info["relations"].most_common(12),
        })
    rows.sort(key=lambda r: (-r["count"], r["lemma"]))

    edge_rows = [
        {"source": s, "target": t, "relation": rel, "count": count}
        for (s, t, rel), count in edges.items()
    ]

    # Search supports both surface form and lemma.
    form_rows = [
        {"form": form, "lemmas": c.most_common(6)}
        for form, c in form_to_lemmas.items()
    ]

    return rows, edge_rows, form_rows


def make_default_network(rows, edges, seed):
    adjacency = defaultdict(set)
    for e in edges:
        adjacency[e["source"]].add(e["target"])
        adjacency[e["target"]].add(e["source"])

    selected = {seed}
    frontier = {seed}
    for _ in range(1):
        nxt = set()
        for n in frontier:
            nxt.update(adjacency.get(n, set()))
        selected.update(list(nxt)[:60])

    net = Network(
        height="700px",
        width="100%",
        bgcolor="#ffffff",
        font_color="#111827",
        directed=True,
        notebook=False,
        cdn_resources="in_line",
    )

    for n in sorted(selected):
        net.add_node(
            n,
            label=n,
            title=f"<b>{html.escape(n)}</b>",
            size=34 if n == seed else 18,
            color="#ff8a65" if n == seed else "#90caf9",
        )

    for e in edges:
        if e["source"] in selected and e["target"] in selected:
            net.add_edge(
                e["source"],
                e["target"],
                label=e["relation"],
                title=f"{e['relation']} | count={e['count']}",
                arrows="to",
            )
    return net.generate_html()


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Input corpus not found: {INPUT_FILE}")

    sentences = read_conllu(INPUT_FILE)
    rows, edges, forms = build_indexes(sentences)
    seed = rows[0]["lemma"] if rows else ""
    network_html = make_default_network(rows, edges, seed)

    payload = {"lemmas": rows, "edges": edges, "forms": forms}
    payload_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    safe_seed = json.dumps(seed, ensure_ascii=False)

    page = f'''<!doctype html>
<html lang="fa" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Concept Language Lab - Interactive Graph V2</title>
<style>
body {{ margin:0; font-family:Segoe UI,Tahoma,sans-serif; background:#f3f4f6; color:#111827; }}
header {{ background:#1f2937; color:white; padding:14px 20px; }}
main {{ display:grid; grid-template-columns:360px 1fr; min-height:calc(100vh - 68px); }}
aside {{ background:#fff; padding:16px; border-left:1px solid #ddd; overflow:auto; }}
section {{ padding:12px; }}
input, select, button {{ width:100%; box-sizing:border-box; padding:9px; margin:4px 0; font-size:14px; }}
button {{ cursor:pointer; border:0; border-radius:6px; background:#2563eb; color:white; }}
button.secondary {{ background:#6b7280; }}
.card {{ background:white; border:1px solid #ddd; border-radius:8px; padding:10px; margin-top:8px; }}
.small {{ color:#6b7280; font-size:12px; }}
.hit {{ cursor:pointer; }}
.hit:hover {{ background:#eff6ff; }}
#network {{ background:#fff; border-radius:8px; overflow:hidden; }}
</style>
</head>
<body>
<header>
  <div style="font-size:20px;font-weight:700">Concept Language Lab â€” Interactive Graph V2</div>
  <div style="opacity:.8;font-size:12px">Persian PerDT development set â€” lemma / form / dependency relation</div>
</header>
<main>
<aside>
  <h3 style="margin-top:0">Ø¬Ø³Øªâ€ŒÙˆØ¬Ùˆ</h3>
  <input id="q" placeholder="ÙˆØ§Ú˜Ù‡ ÛŒØ§ lemma..." oninput="renderMatches()">
  <select id="upos" onchange="renderMatches()">
    <option value="">Ù‡Ù…Ù‡ Ù†Ù‚Ø´â€ŒÙ‡Ø§ÛŒ Ø¯Ø³ØªÙˆØ±ÛŒ</option>
    <option value="NOUN">NOUN</option>
    <option value="VERB">VERB</option>
    <option value="ADJ">ADJ</option>
    <option value="ADV">ADV</option>
    <option value="PRON">PRON</option>
    <option value="PROPN">PROPN</option>
    <option value="DET">DET</option>
    <option value="ADP">ADP</option>
    <option value="NUM">NUM</option>
    <option value="CONJ">CONJ</option>
  </select>
  <button onclick="showSelectedNetwork()">Ù†Ù…Ø§ÛŒØ´ Ø´Ø¨Ú©Ù‡Ù” Ø§Ù†ØªØ®Ø§Ø¨â€ŒØ´Ø¯Ù‡</button>
  <button class="secondary" onclick="showStats()">Ø¢Ù…Ø§Ø±</button>
  <div id="matches" class="card"></div>
  <div id="details" class="card"></div>
</aside>
<section>
  <div id="network">{network_html}</div>
</section>
</main>
<script>
const DATA = {payload_json};
let selectedLemma = {safe_seed};

function esc(s) {{
  return String(s).replace(/[&<>'\"]/g, function(c) {{
    return {{ '&':'&amp;', '<':'&lt;', '>':'&gt;', "'":'&#39;', '\"':'&quot;' }}[c];
  }});
}}
function norm(s) {{ return String(s || '').toLowerCase().trim(); }}
function rowMatches(row, q, upos) {{
  if (upos && !row.upos.some(x => x[0] === upos)) return false;
  if (!q) return true;
  if (norm(row.lemma).includes(q)) return true;
  return row.forms.some(x => norm(x[0]).includes(q));
}}
function renderMatches() {{
  const q = norm(document.getElementById('q').value);
  const upos = document.getElementById('upos').value;
  const hits = DATA.lemmas.filter(r => rowMatches(r,q,upos)).slice(0,40);
  const box = document.getElementById('matches');
  if (!hits.length) {{ box.innerHTML = 'Ù†ØªÛŒØ¬Ù‡â€ŒØ§ÛŒ Ù¾ÛŒØ¯Ø§ Ù†Ø´Ø¯.'; return; }}
  box.innerHTML = '<b>Ù†ØªØ§ÛŒØ¬</b>' + hits.map(r => `
    <div class="card hit" onclick="selectLemma(${{JSON.stringify(r.lemma)}})">
      <b>${{esc(r.lemma)}}</b>
      <div class="small">count=${{r.count}} Â· forms: ${{r.forms.slice(0,4).map(x=>esc(x[0])).join('ØŒ ')}}</div>
    </div>`).join('');
}}
function selectLemma(lemma) {{
  selectedLemma = lemma;
  const r = DATA.lemmas.find(x => x.lemma === lemma);
  if (!r) return;
  const forms = r.forms.map(x=>`<li>${{esc(x[0])}}: ${{x[1]}}</li>`).join('');
  const rels = r.relations.map(x=>`<li>${{esc(x[0])}}: ${{x[1]}}</li>`).join('');
  document.getElementById('details').innerHTML = `
    <h3 style="margin-top:0">${{esc(r.lemma)}}</h3>
    <div><b>count:</b> ${{r.count}}</div>
    <div><b>UPOS:</b> ${{r.upos.map(x=>esc(x[0])+' ('+x[1]+')').join('ØŒ ')}}</div>
    <h4>Ø´Ú©Ù„â€ŒÙ‡Ø§ÛŒ ØµØ±ÙÛŒ</h4><ul>${{forms}}</ul>
    <h4>Ø±ÙˆØ§Ø¨Ø·</h4><ul>${{rels}}</ul>`;
}}
function showStats() {{
  const total = DATA.lemmas.reduce((a,r)=>a+r.count,0);
  document.getElementById('details').innerHTML = `
    <h3>Ø¢Ù…Ø§Ø±</h3>
    <div>lemmaÙ‡Ø§ÛŒ ÛŒÚ©ØªØ§: <b>${{DATA.lemmas.length}}</b></div>
    <div>ÛŒØ§Ù„â€ŒÙ‡Ø§ÛŒ Ø±Ø§Ø¨Ø·Ù‡â€ŒØ§ÛŒ: <b>${{DATA.edges.length}}</b></div>
    <div>Ø±Ø®Ø¯Ø§Ø¯Ù‡Ø§ÛŒ ÙˆØ§Ú˜Ú¯Ø§Ù†ÛŒ: <b>${{total}}</b></div>`;
}}
function showSelectedNetwork() {{
  // The initial graph is the authoritative pyvis network generated by Python.
  // For V2, selection is surfaced in the sidebar and in a compact client-side list.
  const related = DATA.edges.filter(e => e.source === selectedLemma || e.target === selectedLemma)
    .sort((a,b)=>b.count-a.count).slice(0,50);
  const rows = related.map(e => `<div class="card"><b>${{esc(e.source)}}</b> â†’ <b>${{esc(e.target)}}</b><div class="small">${{esc(e.relation)}} Â· count=${{e.count}}</div></div>`).join('');
  document.getElementById('details').innerHTML += '<h4>Ø±ÙˆØ§Ø¨Ø· Ù…Ø³ØªÙ‚ÛŒÙ…</h4>' + (rows || 'Ø±Ø§Ø¨Ø·Ù‡â€ŒØ§ÛŒ ÛŒØ§ÙØª Ù†Ø´Ø¯.');
}}
renderMatches();
selectLemma(selectedLemma);
</script>
</body>
</html>'''

    OUTPUT_FILE.write_text(page, encoding="utf-8")
    print(f"Sentences: {len(sentences):,}")
    print(f"Unique lemmas: {len(rows):,}")
    print(f"Relation edges: {len(edges):,}")
    print(f"Interactive V2: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
