from pathlib import Path
import json
from collections import Counter

import conllu
import networkx as nx
import pandas as pd
import plotly.graph_objects as go

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "external"
RESULTS = ROOT / "results"
GRAPH_DIR = RESULTS / "graphs"
TABLE_DIR = RESULTS / "tables"
GRAPH_DIR.mkdir(parents=True, exist_ok=True)
TABLE_DIR.mkdir(parents=True, exist_ok=True)

candidates = sorted(DATA_DIR.rglob("*.conllu"))
if not candidates:
    raise FileNotFoundError(
        "No .conllu file found under data/external. "
        "Download the UD Persian PerDT corpus first."
    )

path = candidates[0]
print(f"Reading: {path}")

text = path.read_text(encoding="utf-8")
sentences = conllu.parse(text)

edge_counter = Counter()
token_counter = Counter()
relation_counter = Counter()

for sent in sentences:
    for token in sent:
        form = token.get("form")
        head = token.get("head")
        rel = token.get("deprel")
        token_counter[form] += 1
        relation_counter[rel] += 1

        # Universal Dependencies token IDs are integers for normal words.
        if isinstance(head, int) and head > 0:
            head_token = next((t for t in sent if t.get("id") == head), None)
            if head_token:
                head_form = head_token.get("form")
                edge_counter[(head_form, form, rel)] += 1

top_edges = edge_counter.most_common(300)

G = nx.DiGraph()
for (head_form, dep_form, rel), count in top_edges:
    if head_form and dep_form:
        G.add_edge(head_form, dep_form, relation=rel, weight=count)

nodes = list(G.nodes())
index = {n: i for i, n in enumerate(nodes)}

# Simple deterministic layout for portability.
pos = nx.spring_layout(G, seed=42, k=1.4, iterations=80)

edge_x = []
edge_y = []
for u, v in G.edges():
    x0, y0 = pos[u]
    x1, y1 = pos[v]
    edge_x += [x0, x1, None]
    edge_y += [y0, y1, None]

edge_trace = go.Scatter(
    x=edge_x,
    y=edge_y,
    mode="lines",
    line=dict(width=0.7),
    hoverinfo="none",
)

node_x = [pos[n][0] for n in nodes]
node_y = [pos[n][1] for n in nodes]
node_freq = [token_counter[n] for n in nodes]

node_trace = go.Scatter(
    x=node_x,
    y=node_y,
    mode="markers+text",
    text=nodes,
    textposition="top center",
    hovertemplate="%{text}<br>frequency=%{customdata}<extra></extra>",
    customdata=node_freq,
    marker=dict(
        size=[max(8, min(26, 8 + f ** 0.5)) for f in node_freq]
    ),
)

fig = go.Figure(data=[edge_trace, node_trace])
fig.update_layout(
    title="Persian Dependency Graph - first 300 dependency edges",
    xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
    yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
    showlegend=False,
    margin=dict(l=20, r=20, t=60, b=20),
)

html_path = GRAPH_DIR / "perdt_graph.html"
fig.write_html(str(html_path), include_plotlyjs=True)

stats = {
    "source": str(path),
    "sentences": len(sentences),
    "unique_tokens": len(token_counter),
    "graph_nodes": G.number_of_nodes(),
    "graph_edges": G.number_of_edges(),
    "top_dependency_relations": relation_counter.most_common(30),
}

(TABLE_DIR / "stats.json").write_text(
    json.dumps(stats, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

pd.DataFrame(
    relation_counter.most_common(),
    columns=["relation", "count"],
).to_csv(TABLE_DIR / "dependency_relations.csv", index=False, encoding="utf-8-sig")

print("\nDONE")
print(f"Sentences: {len(sentences):,}")
print(f"Unique tokens: {len(token_counter):,}")
print(f"Graph nodes: {G.number_of_nodes():,}")
print(f"Graph edges: {G.number_of_edges():,}")
print(f"Interactive graph: {html_path}")
