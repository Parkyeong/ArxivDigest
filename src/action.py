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


HTML_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>arXiv Digest</title>
<style>
body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 900px; margin: 2em auto; padding: 0 1em; color: #222; }}
h1 {{ border-bottom: 2px solid #333; padding-bottom: 0.3em; }}
h2 {{ color: #c04040; margin-top: 2em; }}
.paper {{ border: 1px solid #ddd; border-radius: 6px; padding: 1em; margin: 1em 0; }}
.paper h3 {{ margin: 0 0 0.4em; font-size: 1.05em; }}
.paper a {{ color: #2060c0; text-decoration: none; }}
.meta {{ color: #666; font-size: 0.9em; margin: 0.3em 0; }}
.scores {{ display: inline-block; background: #eef; padding: 0.2em 0.6em; border-radius: 4px; font-size: 0.85em; margin-right: 0.5em; }}
.reason {{ color: #333; font-style: italic; margin: 0.5em 0; }}
.rating {{ margin-top: 0.6em; }}
.rating button {{ padding: 0.3em 0.7em; margin: 0 2px; border: 1px solid #bbb; background: #fafafa; cursor: pointer; border-radius: 4px; }}
.rating button:hover {{ background: #e0e8ff; }}
.rating button.selected {{ background: #4080d0; color: white; border-color: #4080d0; }}
.rating .skip {{ color: #888; font-size: 0.85em; margin-left: 0.8em; }}
.status {{ color: green; font-size: 0.85em; margin-left: 0.5em; }}
</style>
</head><body>
<h1>arXiv Digest — {date}</h1>
<p class="meta">Core-relevant: {n_core} papers · Cross-domain: {n_transfer} papers · Feedback: {fb_status}</p>
{warning}
<h2>Core Relevant ({n_core})</h2>
{core_html}
<h2>Cross-domain / Transferable ({n_transfer})</h2>
{transfer_html}
<h2>Industry Highlights — Past 14 Days</h2>
<p class="meta">{industry_status}</p>
{industry_html}
<script>
function rate(arxivId, title, score, btn) {{
  fetch('http://127.0.0.1:5005/rate', {{
    method: 'POST',
    headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{arxiv_id: arxivId, title: title, rating: score}})
  }}).then(r => r.json()).then(data => {{
    const status = btn.parentElement.querySelector('.status');
    status.textContent = '✓ saved (' + data.total + ' total)';
    btn.parentElement.querySelectorAll('button').forEach(b => b.classList.remove('selected'));
    btn.classList.add('selected');
  }}).catch(e => {{
    const status = btn.parentElement.querySelector('.status');
    status.textContent = '✗ server not running';
  }});
}}
</script>
</body></html>"""


def _render_paper(paper):
    arxiv_id = paper["main_page"].rsplit("/", 1)[-1]
    title = paper["title"].replace('"', "&quot;")
    buttons = "".join(
        f'<button onclick="rate(\'{arxiv_id}\', &quot;{title}&quot;, {i}, this)">{i}</button>'
        for i in range(1, 11)
    )
    return f"""<div class="paper">
<h3><a href="{paper['main_page']}" target="_blank">{paper['title']}</a></h3>
<div class="meta">{paper['authors']}</div>
<div>
  <span class="scores">core: {paper.get('core_score', '?')}/10</span>
  <span class="scores">transfer: {paper.get('transfer_score', '?')}/10</span>
</div>
<div class="reason">{paper.get('Reasons for match', '')}</div>
<div class="rating">Rate 1-10: {buttons}<span class="skip">(skip if unread — no feedback is saved)</span><span class="status"></span></div>
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
        return "<p>No industry papers found.</p>"
    blocks = []
    for lab, papers in picks.items():
        if not papers:
            blocks.append(f'<h3 style="color:#444;margin-top:1em;">{lab}</h3><p class="meta">No relevant papers in the past 14 days.</p>')
            continue
        lab_html = [f'<h3 style="color:#444;margin-top:1em;">{lab} ({len(papers)})</h3>']
        for p in papers:
            core = p.get("core_score", "?")
            transfer = p.get("transfer_score", "?")
            reason = p.get("Reasons for match", "")
            authors = p.get("authors", "")
            lab_html.append(f'''<div class="paper">
<h3><a href="{p['main_page']}" target="_blank">{p['title']}</a></h3>
<div class="meta">{authors}</div>
<div>
  <span class="scores">core: {core}/10</span>
  <span class="scores">transfer: {transfer}/10</span>
</div>
<div class="reason">{reason}</div>
</div>''')
        blocks.append("\n".join(lab_html))
    return "\n".join(blocks)


def generate_body(topic, categories, interest, threshold, include_industry=True, refresh_industry=False):
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
        scored, hallucination = generate_relevance_score(
            papers,
            query={"interest": interest},
            num_paper_in_prompt=16,
        )
        core_picks, transfer_picks = select_top_papers(scored, n_core=3, n_transfer=7)

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
    if include_industry:
        from industry import load_or_refresh, CACHE_PATH, CACHE_TTL_DAYS
        picks = load_or_refresh(interest, force=refresh_industry)
        industry_html = _render_industry_section(picks)
        if os.path.exists(CACHE_PATH):
            import json as _json
            with open(CACHE_PATH) as f:
                ts = _json.load(f)["timestamp"]
            industry_status = f"Cache from {ts[:10]}, refreshes every {CACHE_TTL_DAYS} days. Use --refresh-industry to force."

    from datetime import date as _date
    html = HTML_TEMPLATE.format(
        date=_date.today().strftime("%d %b %Y"),
        n_core=len(core_picks),
        n_transfer=len(transfer_picks),
        fb_status=fb_status,
        warning=warning,
        core_html="\n".join(_render_paper(p) for p in core_picks) or "<p>No papers matched.</p>",
        transfer_html="\n".join(_render_paper(p) for p in transfer_picks) or "<p>No papers matched.</p>",
        industry_html=industry_html,
        industry_status=industry_status,
    )
    return html


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
    body = generate_body(
        topic, categories, interest, threshold,
        include_industry=not args.no_industry,
        refresh_industry=args.refresh_industry,
    )
    digest_path = os.path.abspath("digest.html")
    with open(digest_path, "w") as f:
        f.write(body)
    print(f"\nDigest written to: {digest_path}")

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
