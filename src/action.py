from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, To, Content

from datetime import date

import argparse
import yaml
import os
from dotenv import load_dotenv
import openai
from relevancy import generate_relevance_score, process_subject_fields
from download_new_papers import get_papers


# Hackathon quality code. Don't judge too harshly.
# Feel free to submit pull requests to improve the code.

topics = {
    "Physics": "",
    "Mathematics": "math",
    "Computer Science": "cs",
    "Quantitative Biology": "q-bio",
    "Quantitative Finance": "q-fin",
    "Statistics": "stat",
    "Electrical Engineering and Systems Science": "eess",
    "Economics": "econ",
}

physics_topics = {
    "Astrophysics": "astro-ph",
    "Condensed Matter": "cond-mat",
    "General Relativity and Quantum Cosmology": "gr-qc",
    "High Energy Physics - Experiment": "hep-ex",
    "High Energy Physics - Lattice": "hep-lat",
    "High Energy Physics - Phenomenology": "hep-ph",
    "High Energy Physics - Theory": "hep-th",
    "Mathematical Physics": "math-ph",
    "Nonlinear Sciences": "nlin",
    "Nuclear Experiment": "nucl-ex",
    "Nuclear Theory": "nucl-th",
    "Physics": "physics",
    "Quantum Physics": "quant-ph",
}


# TODO: surely theres a better way
category_map = {
    "Astrophysics": [
        "Astrophysics of Galaxies",
        "Cosmology and Nongalactic Astrophysics",
        "Earth and Planetary Astrophysics",
        "High Energy Astrophysical Phenomena",
        "Instrumentation and Methods for Astrophysics",
        "Solar and Stellar Astrophysics",
    ],
    "Condensed Matter": [
        "Disordered Systems and Neural Networks",
        "Materials Science",
        "Mesoscale and Nanoscale Physics",
        "Other Condensed Matter",
        "Quantum Gases",
        "Soft Condensed Matter",
        "Statistical Mechanics",
        "Strongly Correlated Electrons",
        "Superconductivity",
    ],
    "General Relativity and Quantum Cosmology": ["None"],
    "High Energy Physics - Experiment": ["None"],
    "High Energy Physics - Lattice": ["None"],
    "High Energy Physics - Phenomenology": ["None"],
    "High Energy Physics - Theory": ["None"],
    "Mathematical Physics": ["None"],
    "Nonlinear Sciences": [
        "Adaptation and Self-Organizing Systems",
        "Cellular Automata and Lattice Gases",
        "Chaotic Dynamics",
        "Exactly Solvable and Integrable Systems",
        "Pattern Formation and Solitons",
    ],
    "Nuclear Experiment": ["None"],
    "Nuclear Theory": ["None"],
    "Physics": [
        "Accelerator Physics",
        "Applied Physics",
        "Atmospheric and Oceanic Physics",
        "Atomic and Molecular Clusters",
        "Atomic Physics",
        "Biological Physics",
        "Chemical Physics",
        "Classical Physics",
        "Computational Physics",
        "Data Analysis, Statistics and Probability",
        "Fluid Dynamics",
        "General Physics",
        "Geophysics",
        "History and Philosophy of Physics",
        "Instrumentation and Detectors",
        "Medical Physics",
        "Optics",
        "Physics and Society",
        "Physics Education",
        "Plasma Physics",
        "Popular Physics",
        "Space Physics",
    ],
    "Quantum Physics": ["None"],
    "Mathematics": [
        "Algebraic Geometry",
        "Algebraic Topology",
        "Analysis of PDEs",
        "Category Theory",
        "Classical Analysis and ODEs",
        "Combinatorics",
        "Commutative Algebra",
        "Complex Variables",
        "Differential Geometry",
        "Dynamical Systems",
        "Functional Analysis",
        "General Mathematics",
        "General Topology",
        "Geometric Topology",
        "Group Theory",
        "History and Overview",
        "Information Theory",
        "K-Theory and Homology",
        "Logic",
        "Mathematical Physics",
        "Metric Geometry",
        "Number Theory",
        "Numerical Analysis",
        "Operator Algebras",
        "Optimization and Control",
        "Probability",
        "Quantum Algebra",
        "Representation Theory",
        "Rings and Algebras",
        "Spectral Theory",
        "Statistics Theory",
        "Symplectic Geometry",
    ],
    "Computer Science": [
        "Artificial Intelligence",
        "Computation and Language",
        "Computational Complexity",
        "Computational Engineering, Finance, and Science",
        "Computational Geometry",
        "Computer Science and Game Theory",
        "Computer Vision and Pattern Recognition",
        "Computers and Society",
        "Cryptography and Security",
        "Data Structures and Algorithms",
        "Databases",
        "Digital Libraries",
        "Discrete Mathematics",
        "Distributed, Parallel, and Cluster Computing",
        "Emerging Technologies",
        "Formal Languages and Automata Theory",
        "General Literature",
        "Graphics",
        "Hardware Architecture",
        "Human-Computer Interaction",
        "Information Retrieval",
        "Information Theory",
        "Logic in Computer Science",
        "Machine Learning",
        "Mathematical Software",
        "Multiagent Systems",
        "Multimedia",
        "Networking and Internet Architecture",
        "Neural and Evolutionary Computing",
        "Numerical Analysis",
        "Operating Systems",
        "Other Computer Science",
        "Performance",
        "Programming Languages",
        "Robotics",
        "Social and Information Networks",
        "Software Engineering",
        "Sound",
        "Symbolic Computation",
        "Systems and Control",
    ],
    "Quantitative Biology": [
        "Biomolecules",
        "Cell Behavior",
        "Genomics",
        "Molecular Networks",
        "Neurons and Cognition",
        "Other Quantitative Biology",
        "Populations and Evolution",
        "Quantitative Methods",
        "Subcellular Processes",
        "Tissues and Organs",
    ],
    "Quantitative Finance": [
        "Computational Finance",
        "Economics",
        "General Finance",
        "Mathematical Finance",
        "Portfolio Management",
        "Pricing of Securities",
        "Risk Management",
        "Statistical Finance",
        "Trading and Market Microstructure",
    ],
    "Statistics": [
        "Applications",
        "Computation",
        "Machine Learning",
        "Methodology",
        "Other Statistics",
        "Statistics Theory",
    ],
    "Electrical Engineering and Systems Science": [
        "Audio and Speech Processing",
        "Image and Video Processing",
        "Signal Processing",
        "Systems and Control",
    ],
    "Economics": ["Econometrics", "General Economics", "Theoretical Economics"],
}


BASE_CSS = """body { font-family: -apple-system, system-ui, sans-serif; max-width: 900px; margin: 2em auto; padding: 0 1em; color: #222; }
h1 { border-bottom: 2px solid #333; padding-bottom: 0.3em; }
h2 { color: #c04040; margin-top: 2em; }
h3.lab { color: #444; margin-top: 1em; border-bottom: 1px solid #ddd; padding-bottom: 0.2em; }
nav.topnav { display: flex; gap: 1em; padding: 0.8em 0; border-bottom: 1px solid #eee; margin-bottom: 1em; }
nav.topnav a { color: #2060c0; text-decoration: none; padding: 0.3em 0.8em; border-radius: 4px; }
nav.topnav a.active { background: #2060c0; color: white; }
nav.topnav a:hover:not(.active) { background: #eef; }
.paper { border: 1px solid #ddd; border-radius: 6px; padding: 1em; margin: 1em 0; }
.paper h3 { margin: 0 0 0.4em; font-size: 1.05em; }
.paper a { color: #2060c0; text-decoration: none; }
.meta { color: #666; font-size: 0.9em; margin: 0.3em 0; }
.scores { display: inline-block; background: #eef; padding: 0.2em 0.6em; border-radius: 4px; font-size: 0.85em; margin-right: 0.5em; }
.source-tag { display: inline-block; background: #fed; color: #a50; padding: 0.1em 0.5em; border-radius: 3px; font-size: 0.8em; margin-left: 0.4em; }
.reason { color: #333; font-style: italic; margin: 0.5em 0; }
.rating { margin-top: 0.6em; }
.rating-label { font-size: 0.9em; color: #666; margin-right: 0.4em; }
.rating button { padding: 0.3em 0.7em; margin: 0 2px; border: 1px solid #bbb; background: #fafafa; cursor: pointer; border-radius: 4px; font-size: 0.9em; }
.rating button:hover { background: #e0e8ff; }
.rating button.selected { background: #4080d0; color: white; border-color: #4080d0; }
.rating .skip { color: #888; font-size: 0.85em; margin-left: 0.8em; }
.status { color: green; font-size: 0.85em; margin-left: 0.5em; }
.comment { margin-top: 0.5em; }
.comment textarea { width: 100%; min-height: 2.2em; padding: 0.3em; font-family: inherit; font-size: 0.9em; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }
.search-box { width: 100%; padding: 0.5em; margin: 1em 0; border: 1px solid #ccc; border-radius: 4px; font-size: 1em; box-sizing: border-box; }
.empty { color: #999; text-align: center; padding: 2em; font-style: italic; }
.stage-1-shown { background: #f5f5f0; font-size: 0.85em; padding: 0.4em 0.6em; border-radius: 4px; margin-top: 0.3em; color: #555; }"""


def _nav_html(active):
    """Render top navigation with `active` = 'daily' | 'queue' | 'library'."""
    items = [("daily", "digest.html", "📰 Daily"),
             ("queue", "queue.html", "📖 Reading Queue"),
             ("library", "library.html", "📚 My Library")]
    links = []
    for key, href, label in items:
        cls = ' class="active"' if key == active else ''
        links.append(f'<a href="{href}"{cls}>{label}</a>')
    return f'<nav class="topnav">{"".join(links)}</nav>'


RATING_JS = """
async function loadExistingRatings(stage) {
  try {
    const r = await fetch('http://127.0.0.1:5005/ratings');
    const data = await r.json();
    document.querySelectorAll('.paper').forEach(pdiv => {
      const aid = pdiv.dataset.arxivId;
      if (!aid || !data[aid]) return;
      const entry = data[aid][stage];
      if (!entry) return;
      const btn = pdiv.querySelector('.rating button[data-score="' + entry.rating + '"]');
      if (btn) btn.classList.add('selected');
      const status = pdiv.querySelector('.status');
      if (status) status.textContent = '✓ rated ' + entry.rating + '/10';
      const ta = pdiv.querySelector('.comment textarea');
      if (ta && entry.comment) ta.value = entry.comment;
    });
  } catch (e) { console.log('Ratings restore skipped:', e); }
}

function rate(arxivId, score, btn, stage) {
  const pdiv = btn.closest('.paper');
  const comment = pdiv.querySelector('.comment textarea').value;
  const metadata = pdiv.dataset.metadata ? JSON.parse(pdiv.dataset.metadata) : null;
  const title = metadata ? metadata.title : '';
  fetch('http://127.0.0.1:5005/rate', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({arxiv_id: arxivId, title: title, rating: score, comment: comment, stage: stage, metadata: metadata})
  }).then(r => r.json()).then(data => {
    const status = pdiv.querySelector('.status');
    status.textContent = '✓ saved (' + data.total + ' total)';
    pdiv.querySelectorAll('.rating button').forEach(b => b.classList.remove('selected'));
    btn.classList.add('selected');
  }).catch(e => {
    const status = pdiv.querySelector('.status');
    status.textContent = '✗ server not running';
  });
}
"""


HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>arXiv Digest — {date}</title>
<style>
{css}
</style>
</head><body>
{nav}
<h1>📰 Daily Digest — {date}</h1>
<p class="meta">Top {n_daily} today · Industry: {n_industry} · Classics: {n_classic} · Feedback: {fb_status}</p>
{warning}

<h2>Top Picks of Today</h2>
<h3 class="lab">Core Relevant ({n_core})</h3>
{core_html}
<h3 class="lab">Cross-domain / Transferable ({n_transfer})</h3>
{transfer_html}

<h2>🏭 Industry Highlights — Past 14 Days</h2>
<p class="meta">{industry_status}</p>
{industry_html}

<h2>📚 Classic Papers in Your Field</h2>
<p class="meta">{classics_status}</p>
{classics_html}

<script>
{rating_js}
window.addEventListener('DOMContentLoaded', () => loadExistingRatings(1));
</script>
</body></html>"""


QUEUE_HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Reading Queue</title>
<style>
{css}
</style>
</head><body>
{nav}
<h1>📖 Reading Queue</h1>
<p class="meta">Papers you Stage-1-rated ≥7, waiting for deep reading. Rate again after reading (Stage-2) to move them to Library or discard.</p>
<p class="meta">Auto-expires after 30 days — expired papers re-enter the classic candidate pool.</p>
<div id="queue-list" class="empty">Loading...</div>
<script>
{rating_js}

function renderPaper(p) {{
  const buttons = Array.from({{length: 10}}, (_, i) => i + 1).map(i =>
    `<button data-score="${{i}}" onclick="rate('${{p.arxiv_id}}', ${{i}}, this, 2)">${{i}}</button>`
  ).join('');
  const metaJson = JSON.stringify(p).replace(/'/g, '&#39;');
  const safeTitle = (p.title || '').replace(/</g, '&lt;');
  const safeReason = (p.reason || '').replace(/</g, '&lt;');
  const safeAuthors = (p.authors || '').replace(/</g, '&lt;');
  const core = p.core_score ?? '?';
  const transfer = p.transfer_score ?? '?';
  const s1rating = p.stage_1_rating ?? '?';
  const s1comment = p.stage_1_comment ? ' · note: ' + p.stage_1_comment : '';
  const source = p.source ? `<span class="source-tag">${{p.source}}</span>` : '';
  return `<div class="paper" data-arxiv-id="${{p.arxiv_id}}" data-metadata='${{metaJson}}'>
<h3><a href="${{p.main_page}}" target="_blank">${{safeTitle}}</a>${{source}}</h3>
<div class="meta">${{safeAuthors}}</div>
<div><span class="scores">core: ${{core}}/10</span><span class="scores">transfer: ${{transfer}}/10</span></div>
<div class="reason">${{safeReason}}</div>
<div class="stage-1-shown">Your Stage-1 (scan): ${{s1rating}}/10${{s1comment}}</div>
<div class="rating"><span class="rating-label">Stage-2 (after reading):</span>${{buttons}}<span class="skip">(skip — stays in queue)</span><span class="status"></span></div>
<div class="comment"><textarea placeholder="Your notes after reading"></textarea></div>
</div>`;
}}

async function loadQueue() {{
  try {{
    const r = await fetch('http://127.0.0.1:5005/queue');
    const data = await r.json();
    const list = document.getElementById('queue-list');
    if (!data.length) {{
      list.className = 'empty';
      list.textContent = 'Queue is empty. Stage-1 rate papers ≥7 on Daily to populate.';
      return;
    }}
    list.className = '';
    list.innerHTML = data.map(renderPaper).join('');
    loadExistingRatings(2);
  }} catch (e) {{
    document.getElementById('queue-list').textContent = '✗ Feedback server not running. Run: python feedback_server.py';
  }}
}}

window.addEventListener('DOMContentLoaded', loadQueue);
</script>
</body></html>"""


LIBRARY_HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>My Library</title>
<style>
{css}
.sort-row {{ margin: 0.5em 0; color: #666; font-size: 0.9em; }}
.sort-row button {{ padding: 0.2em 0.6em; margin: 0 0.2em; border: 1px solid #bbb; background: #fafafa; cursor: pointer; border-radius: 3px; font-size: 0.85em; }}
.sort-row button.active {{ background: #4080d0; color: white; border-color: #4080d0; }}
</style>
</head><body>
{nav}
<h1>📚 My Library</h1>
<p class="meta">Papers you Stage-2-rated ≥7 after deep reading — your curated research pool.</p>
<input type="text" id="search" class="search-box" placeholder="Search title, abstract, or notes...">
<div class="sort-row">Sort by:
  <button data-sort="rating" class="active">Your rating</button>
  <button data-sort="date">Date added</button>
  <button data-sort="core">Core score</button>
</div>
<div id="library-list" class="empty">Loading...</div>
<script>
let allPapers = [];
let currentSort = 'rating';

function renderLibraryPaper(p) {{
  const safeTitle = (p.title || '').replace(/</g, '&lt;');
  const safeAuthors = (p.authors || '').replace(/</g, '&lt;');
  const core = p.core_score ?? '?';
  const transfer = p.transfer_score ?? '?';
  const s2rating = p.stage_2_rating ?? '?';
  const s2comment = p.stage_2_comment ? `<div class="reason">💭 ${{p.stage_2_comment}}</div>` : '';
  const note = p.note ? `<div class="meta">📌 ${{p.note}}</div>` : '';
  const source = p.source ? `<span class="source-tag">${{p.source}}</span>` : '';
  const dateStr = p.stage_2_timestamp ? p.stage_2_timestamp.slice(0, 10) : '';
  const link = p.main_page || '#';
  return `<div class="paper">
<h3><a href="${{link}}" target="_blank">${{safeTitle}}</a>${{source}}</h3>
<div class="meta">${{safeAuthors}}</div>
<div><span class="scores">your rating: ${{s2rating}}/10</span><span class="scores">core: ${{core}}/10</span><span class="scores">transfer: ${{transfer}}/10</span><span class="meta" style="margin-left:0.5em;">added ${{dateStr}}</span></div>
${{s2comment}}
${{note}}
</div>`;
}}

function sortPapers(papers, key) {{
  const copy = [...papers];
  if (key === 'rating') copy.sort((a, b) => (b.stage_2_rating || 0) - (a.stage_2_rating || 0));
  else if (key === 'date') copy.sort((a, b) => (b.stage_2_timestamp || '').localeCompare(a.stage_2_timestamp || ''));
  else if (key === 'core') copy.sort((a, b) => (b.core_score || 0) - (a.core_score || 0));
  return copy;
}}

function render() {{
  const q = document.getElementById('search').value.trim().toLowerCase();
  let list = allPapers;
  if (q) {{
    list = list.filter(p => {{
      const hay = ((p.title || '') + ' ' + (p.abstract || '') + ' ' + (p.stage_2_comment || '') + ' ' + (p.note || '')).toLowerCase();
      return hay.includes(q);
    }});
  }}
  list = sortPapers(list, currentSort);
  const container = document.getElementById('library-list');
  if (!list.length) {{
    container.className = 'empty';
    container.textContent = q ? 'No matches.' : 'Library is empty. Read and Stage-2-rate papers ≥7 from Reading Queue to populate.';
    return;
  }}
  container.className = '';
  container.innerHTML = list.map(renderLibraryPaper).join('');
}}

async function loadLibrary() {{
  try {{
    const r = await fetch('http://127.0.0.1:5005/library');
    allPapers = await r.json();
    render();
  }} catch (e) {{
    document.getElementById('library-list').textContent = '✗ Feedback server not running.';
  }}
}}

document.getElementById('search').addEventListener('input', render);
document.querySelectorAll('.sort-row button').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('.sort-row button').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    currentSort = btn.dataset.sort;
    render();
  }});
}});

window.addEventListener('DOMContentLoaded', loadLibrary);
</script>
</body></html>"""


def _paper_metadata_for_embed(paper, source=""):
    """Return a sanitized dict to embed in data-metadata for the server to persist."""
    return {
        "arxiv_id": paper.get("arxiv_id") or (paper.get("main_page", "").rsplit("/", 1)[-1] if paper.get("main_page") else ""),
        "title": paper.get("title", ""),
        "authors": paper.get("authors", ""),
        "abstract": paper.get("abstract", ""),
        "main_page": paper.get("main_page", ""),
        "core_score": paper.get("core_score"),
        "transfer_score": paper.get("transfer_score"),
        "reason": paper.get("Reasons for match") or paper.get("reason", ""),
        "source": source,
    }


def _render_paper(paper, stage=1, source=""):
    main_page = paper.get("main_page", "")
    arxiv_id = paper.get("arxiv_id") or (main_page.rsplit("/", 1)[-1] if main_page else "")
    if not arxiv_id:
        arxiv_id = main_page or paper.get("title", "")
    meta = _paper_metadata_for_embed(paper, source=source)
    meta["arxiv_id"] = arxiv_id
    import json as _json
    meta_attr = _json.dumps(meta, ensure_ascii=False).replace("'", "&#39;").replace('"', "&quot;")
    buttons = "".join(
        f'<button data-score="{i}" onclick="rate(\'{arxiv_id}\', {i}, this, {stage})">{i}</button>'
        for i in range(1, 11)
    )
    core = paper.get("core_score", "?")
    transfer = paper.get("transfer_score", "?")
    reason = paper.get("Reasons for match") or paper.get("reason", "")
    authors = paper.get("authors", "")
    label = "Stage-1 (scan):" if stage == 1 else "Stage-2 (after reading):"
    skip = "(skip — stays as unrated)" if stage == 1 else "(skip — stays in queue)"
    source_tag = f'<span class="source-tag">{source}</span>' if source else ""
    return f"""<div class="paper" data-arxiv-id="{arxiv_id}" data-metadata="{meta_attr}">
<h3><a href="{main_page}" target="_blank">{paper['title']}</a>{source_tag}</h3>
<div class="meta">{authors}</div>
<div>
  <span class="scores">core: {core}/10</span>
  <span class="scores">transfer: {transfer}/10</span>
</div>
<div class="reason">{reason}</div>
<div class="rating"><span class="rating-label">{label}</span>{buttons}<span class="skip">{skip}</span><span class="status"></span></div>
<div class="comment"><textarea placeholder="Optional note (saved with your rating)"></textarea></div>
</div>"""


def select_top_papers(scored_papers, n_core=3, n_transfer=7):
    """Pick top n_core by core_score, then top n_transfer by transfer_score excluding already-picked."""
    by_core = sorted(scored_papers, key=lambda p: p.get("core_score", 0), reverse=True)
    core_picks = by_core[:n_core]
    picked_ids = {p["main_page"] for p in core_picks}
    remaining = [p for p in scored_papers if p["main_page"] not in picked_ids]
    by_transfer = sorted(remaining, key=lambda p: p.get("transfer_score", 0), reverse=True)
    transfer_picks = by_transfer[:n_transfer]
    return core_picks, transfer_picks


def _render_industry_section(picks):
    if not picks:
        return "<p>No industry papers found.</p>", 0
    blocks = []
    total = 0
    for lab, papers in picks.items():
        if not papers:
            blocks.append(f'<h3 class="lab">{lab}</h3><p class="meta">No relevant papers in the past 14 days.</p>')
            continue
        total += len(papers)
        lab_html = [f'<h3 class="lab">{lab} ({len(papers)})</h3>']
        for p in papers:
            lab_html.append(_render_paper(p, stage=1, source=f"industry/{lab}"))
        blocks.append("\n".join(lab_html))
    return "\n".join(blocks), total


def _render_classics_section(picks):
    if not picks:
        return "<p>No classic papers selected yet.</p>", 0
    return "\n".join(_render_paper(p, stage=1, source="classics") for p in picks), len(picks)


def generate_body(topic, categories, interest, threshold,
                  include_industry=True, refresh_industry=False,
                  include_classics=True, refresh_classics=False):
    if topic == "Physics":
        raise RuntimeError("You must choose a physics subtopic.")
    elif topic in physics_topics:
        abbr = physics_topics[topic]
    elif topic in topics:
        abbr = topics[topic]
    else:
        raise RuntimeError(f"Invalid topic {topic}")
    if categories:
        for category in categories:
            if category not in category_map[topic]:
                raise RuntimeError(f"{category} is not a category of {topic}")
        papers = get_papers(abbr)
        papers = [
            t for t in papers
            if bool(set(process_subject_fields(t["subjects"])) & set(categories))
        ]
    else:
        papers = get_papers(abbr)

    if not interest:
        core_picks = papers[:3]
        transfer_picks = papers[3:10]
        hallucination = False
    else:
        from datetime import date as _date, timedelta
        import json as _json
        scored_dir = os.path.join(os.path.dirname(__file__), "data")
        os.makedirs(scored_dir, exist_ok=True)
        today_str = _date.today().strftime("%Y-%m-%d")
        scored_path = os.path.join(scored_dir, f"scored_{today_str}.json")

        # Auto-purge scored caches older than 7 days
        cutoff = _date.today() - timedelta(days=7)
        for fname in os.listdir(scored_dir):
            if fname.startswith("scored_") and fname.endswith(".json"):
                try:
                    d = _date.fromisoformat(fname[len("scored_"):-len(".json")])
                    if d < cutoff:
                        os.remove(os.path.join(scored_dir, fname))
                        print(f"Purged old scored cache: {fname}")
                except Exception:
                    pass

        if os.path.exists(scored_path):
            print(f"Using today's scored cache → {scored_path}")
            with open(scored_path) as f:
                cached = _json.load(f)
            scored = cached["scored"]
            hallucination = cached.get("hallucination", False)
        else:
            scored, hallucination = generate_relevance_score(
                papers,
                query={"interest": interest},
                num_paper_in_prompt=16,
            )
            with open(scored_path, "w") as f:
                _json.dump(
                    {"scored": scored, "hallucination": hallucination},
                    f, ensure_ascii=False,
                )
            print(f"Saved scored cache → {scored_path}")

        core_picks, transfer_picks = select_top_papers(scored, n_core=2, n_transfer=3)

    from relevancy import load_feedback_examples
    pos, neg = load_feedback_examples()
    if pos or neg:
        fb_status = f"{len(pos)} positive, {len(neg)} negative examples in use"
    else:
        fb_status = "inactive (need ≥5 ratings to activate)"

    warning = ""
    if hallucination:
        warning = '<p style="color:#c44;">⚠ Warning: model output was partially malformed; some scores may be missing.</p>'

    industry_html = ""
    industry_status = "Industry section disabled."
    n_industry = 0
    if include_industry:
        from industry import load_or_refresh as industry_load, CACHE_PATH as IND_PATH, CACHE_TTL_DAYS as IND_TTL
        picks = industry_load(interest, force=refresh_industry)
        industry_html, n_industry = _render_industry_section(picks)
        if os.path.exists(IND_PATH):
            import json as _json
            with open(IND_PATH) as f:
                ts = _json.load(f)["timestamp"]
            industry_status = f"Cache from {ts[:10]}, auto-refresh every {IND_TTL} days. Use --refresh-industry to force."

    classics_html = ""
    classics_status = "Classics section disabled."
    n_classic = 0
    if include_classics:
        from classics import load_or_refresh as classics_load, CACHE_PATH as CLS_PATH, CACHE_TTL_DAYS as CLS_TTL
        feedback_path = os.path.join(os.path.dirname(__file__), "..", "feedback.jsonl")
        classic_picks = classics_load(interest, feedback_path, force=refresh_classics)
        classics_html, n_classic = _render_classics_section(classic_picks)
        if os.path.exists(CLS_PATH):
            import json as _json
            with open(CLS_PATH) as f:
                ts = _json.load(f)["timestamp"]
            classics_status = f"Cache from {ts[:10]}, auto-refresh every {CLS_TTL} days. Use --refresh-classics to force."

    from datetime import date as _date
    html = HTML_TEMPLATE.format(
        css=BASE_CSS,
        nav=_nav_html("daily"),
        rating_js=RATING_JS,
        date=_date.today().strftime("%d %b %Y"),
        n_daily=len(core_picks) + len(transfer_picks),
        n_core=len(core_picks),
        n_transfer=len(transfer_picks),
        n_industry=n_industry,
        n_classic=n_classic,
        fb_status=fb_status,
        warning=warning,
        core_html="\n".join(_render_paper(p, stage=1, source="daily/core") for p in core_picks) or "<p>No papers matched.</p>",
        transfer_html="\n".join(_render_paper(p, stage=1, source="daily/transfer") for p in transfer_picks) or "<p>No papers matched.</p>",
        industry_html=industry_html,
        industry_status=industry_status,
        classics_html=classics_html,
        classics_status=classics_status,
    )
    queue_html = QUEUE_HTML_TEMPLATE.format(
        css=BASE_CSS, nav=_nav_html("queue"), rating_js=RATING_JS,
    )
    library_html = LIBRARY_HTML_TEMPLATE.format(
        css=BASE_CSS, nav=_nav_html("library"),
    )
    return html, queue_html, library_html


if __name__ == "__main__":
    # Load the .env file.
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--config", help="yaml config file to use", default="config.yaml"
    )
    parser.add_argument(
        "--refresh-industry", action="store_true",
        help="Force refresh of industry section cache (normally auto-refreshes every 7 days)"
    )
    parser.add_argument(
        "--no-industry", action="store_true",
        help="Skip the industry highlights section"
    )
    parser.add_argument(
        "--refresh-classics", action="store_true",
        help="Force refresh of classic papers cache (normally auto-refreshes every 30 days)"
    )
    parser.add_argument(
        "--no-classics", action="store_true",
        help="Skip the classics section"
    )
    args = parser.parse_args()
    with open(args.config, "r") as f:
        config = yaml.safe_load(f)

    if "OPENAI_API_KEY" not in os.environ:
        raise RuntimeError("No openai api key found")
    openai.api_key = os.environ.get("OPENAI_API_KEY")

    topic = config["topic"]
    categories = config["categories"]
    from_email = os.environ.get("FROM_EMAIL")
    to_email = os.environ.get("TO_EMAIL")
    threshold = config["threshold"]
    interest = config["interest"]
    digest_html, queue_html, library_html = generate_body(
        topic, categories, interest, threshold,
        include_industry=not args.no_industry,
        refresh_industry=args.refresh_industry,
        include_classics=not args.no_classics,
        refresh_classics=args.refresh_classics,
    )
    digest_path = os.path.abspath("digest.html")
    queue_path = os.path.abspath("queue.html")
    library_path = os.path.abspath("library.html")
    with open(digest_path, "w") as f: f.write(digest_html)
    with open(queue_path, "w") as f: f.write(queue_html)
    with open(library_path, "w") as f: f.write(library_html)
    print(f"\nDigest   → {digest_path}")
    print(f"Queue    → {queue_path}")
    print(f"Library  → {library_path}")
    body = digest_html  # for backward-compat (email sending etc.)

    # Start feedback server in background and open browser
    import threading, webbrowser
    from feedback_server import app as feedback_app
    def _run_server():
        feedback_app.run(host="127.0.0.1", port=5005, debug=False, use_reloader=False)
    server_thread = threading.Thread(target=_run_server, daemon=True)
    server_thread.start()
    print("Feedback server running on http://127.0.0.1:5005")
    webbrowser.open(f"file://{digest_path}")
    print("Opened digest in browser. Rate papers — ratings save automatically.")
    print("Press Ctrl+C when done to exit.\n")

    if os.environ.get("SENDGRID_API_KEY", None):
        sg = SendGridAPIClient(api_key=os.environ.get("SENDGRID_API_KEY"))
        from_email = Email(from_email)  # Change to your verified sender
        to_email = To(to_email)
        subject = date.today().strftime("Personalized arXiv Digest, %d %b %Y")
        content = Content("text/html", body)
        mail = Mail(from_email, to_email, subject, content)
        mail_json = mail.get()

        # Send an HTTP POST request to /mail/send
        response = sg.client.mail.send.post(request_body=mail_json)
        if response.status_code >= 200 and response.status_code <= 300:
            print("Send test email: Success!")
        else:
            print("Send test email: Failure ({response.status_code}, {response.text})")
    else:
        print("No sendgrid api key found. Skipping email")

    # Keep main thread alive so feedback server stays up
    try:
        while True:
            server_thread.join(timeout=1)
    except KeyboardInterrupt:
        print("\nExiting. Feedback saved to ../feedback.jsonl")
