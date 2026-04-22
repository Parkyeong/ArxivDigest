"""Classic papers module.

Workflow:
  1. Ask LLM (gpt-4o-mini) to list classic/influential papers matching user interest
     + high-rated feedback seeds, with arXiv IDs.
  2. Verify each arXiv ID exists and fetch title/authors/abstract.
  3. Expand with Semantic Scholar's recommendation API (optional, best-effort).
  4. Score all with the existing dual-score pipeline.
  5. Pick top 10 by max(core, transfer), excluding papers the user already rated.
  6. Cache to classics_cache.json with 30-day TTL.
"""
import json
import os
import re
import time
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup

CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "classics_cache.json")
CACHE_TTL_DAYS = 7
TOP_K = 10
LLM_CANDIDATE_COUNT = 25
SS_EXPAND_PER_SEED = 3
MIN_SCORE = 6


def load_feedback_seeds(feedback_path, min_rating=8):
    if not os.path.exists(feedback_path):
        return [], set()
    positives = []
    rated_ids = set()
    with open(feedback_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            e = json.loads(line)
            rated_ids.add(e.get("arxiv_id", ""))
            if e.get("rating", 0) >= min_rating:
                positives.append(e)
    return positives, rated_ids


def llm_generate_classics(interest, seed_papers, model_name="anthropic/claude-opus-4.6"):
    """Ask LLM to list classic papers via OpenRouter.

    Returns list of {"arxiv_id", "title", "reason", "rank"} ordered by
    recommended reading sequence (foundational first, then specialized).
    """
    from openai import OpenAI

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError("OPENROUTER_API_KEY not set — cannot generate classics.")
    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
    )

    seed_str = ""
    if seed_papers:
        seed_str = "\n\nThe user already loves these papers (use them to infer direction):\n"
        for s in seed_papers:
            seed_str += f"  - \"{s['title']}\""
            if s.get("note"):
                seed_str += f" ({s['note']})"
            seed_str += "\n"

    prompt = f"""You are a PhD research advisor. Your student is an EARLY-STAGE PhD who
needs to rapidly build a knowledge foundation in their research direction.
They need papers that form the intellectual backbone of this area — not a
broad survey, but a carefully curated reading list ordered from foundational
to specialized.

Based on the student's research interest below, recommend {LLM_CANDIDATE_COUNT} papers.

## Selection criteria (in priority order)
1. FOUNDATIONAL papers that define the core concepts the student must understand
   (e.g., the paper that introduced ReAct, MCTS for LLM agents, multi-agent debate)
2. LANDMARK papers with high citation impact that shaped the field's direction
3. KEY RECENT papers (2024-2025) that represent the current frontier and are
   directly on the student's research proposition

## Ordering
Return papers in RECOMMENDED READING ORDER — the order a PhD student should
read them to build understanding progressively:
  - Start with foundational/prerequisite works
  - Then core methodological papers
  - Then recent frontier papers closest to the student's specific proposition

Student's research interest:
{interest}
{seed_str}

Return a JSON array. Each entry MUST have:
  - "arxiv_id": the arXiv ID in the form "YYMM.NNNNN" (e.g. "2310.06117").
    If you are not sure of the exact ID, omit the entry — do NOT make up IDs.
  - "title": the paper title.
  - "reason": 1 sentence on why this paper matters for this student's direction.

Only include papers you are confident exist on arXiv. Return ONLY the JSON array, no prose, no markdown fences."""

    resp = client.chat.completions.create(
        model=model_name,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=4000,
    )
    text = resp.choices[0].message.content.strip()
    text = re.sub(r"```(?:json)?", "", text).strip()
    try:
        items = json.loads(text)
    except Exception as e:
        print(f"  LLM output parse failed: {e}")
        return []
    valid = []
    for rank, it in enumerate(items):
        aid = str(it.get("arxiv_id", "")).strip()
        if re.match(r"^\d{4}\.\d{4,5}$", aid):
            valid.append({
                "arxiv_id": aid,
                "title": it.get("title", ""),
                "reason": it.get("reason", ""),
                "rank": rank,
            })
    print(f"  LLM proposed {len(valid)} candidates with well-formed arxiv IDs")
    return valid


def fetch_arxiv_by_id(arxiv_id):
    """Fetch title/authors/abstract from arxiv API. Returns None on failure."""
    url = f"http://export.arxiv.org/api/query?id_list={arxiv_id}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
    except Exception:
        return None
    soup = BeautifulSoup(resp.text, features="xml")
    entry = soup.find("entry")
    if not entry:
        return None
    title = entry.find("title")
    summary = entry.find("summary")
    if not title or not summary:
        return None
    title_text = re.sub(r"\s+", " ", title.text).strip()
    # arxiv returns an error placeholder if ID not found
    if "Error" in title_text or not title_text:
        return None
    return {
        "arxiv_id": arxiv_id,
        "title": title_text,
        "authors": ", ".join(a.find("name").text for a in entry.find_all("author")),
        "abstract": re.sub(r"\s+", " ", summary.text).strip(),
        "main_page": f"https://arxiv.org/abs/{arxiv_id}",
    }


def verify_candidates(candidates):
    """Parallel-verify each candidate via arxiv API."""
    verified = []
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fetch_arxiv_by_id, c["arxiv_id"]): c for c in candidates}
        for fut in as_completed(futures):
            try:
                paper = fut.result()
                if paper:
                    verified.append(paper)
            except Exception:
                continue
    return verified


def ss_recommendations(arxiv_id, limit=SS_EXPAND_PER_SEED):
    """Get related papers from Semantic Scholar. Best-effort, returns list of {arxiv_id, title, ...}."""
    # Get paperId from arxiv
    try:
        r = requests.get(
            f"https://api.semanticscholar.org/graph/v1/paper/arXiv:{arxiv_id}",
            params={"fields": "paperId"},
            timeout=10,
        )
        if r.status_code != 200:
            return []
        paper_id = r.json().get("paperId")
        if not paper_id:
            return []
        time.sleep(0.5)  # be polite
        r2 = requests.get(
            f"https://api.semanticscholar.org/recommendations/v1/papers/forpaper/{paper_id}",
            params={"fields": "title,externalIds,abstract,authors", "limit": limit},
            timeout=10,
        )
        if r2.status_code != 200:
            return []
        out = []
        for p in r2.json().get("recommendedPapers", []):
            ext = p.get("externalIds") or {}
            aid = ext.get("ArXiv")
            if not aid:
                continue
            out.append({
                "arxiv_id": aid,
                "title": p.get("title", ""),
                "authors": ", ".join(a.get("name", "") for a in (p.get("authors") or [])),
                "abstract": (p.get("abstract") or "").strip(),
                "main_page": f"https://arxiv.org/abs/{aid}",
            })
        return out
    except Exception:
        return []


def expand_with_ss(seeds):
    """Expand each seed with Semantic Scholar recommendations."""
    expanded = []
    for s in seeds:
        recs = ss_recommendations(s["arxiv_id"])
        expanded.extend(recs)
    print(f"  Semantic Scholar yielded {len(expanded)} additional candidates")
    return expanded


def load_expired_queue_papers(feedback_path, metadata_path, expiry_days=30, min_rating=7):
    """Return papers the user Stage-1-rated ≥7 that are older than expiry_days and never Stage-2-rated.

    These come from queue.jsonl-style derivation: we read feedback.jsonl + papers_metadata.jsonl.
    """
    if not os.path.exists(feedback_path):
        return []
    # Build {arxiv_id: {stage: latest_entry}}
    entries = []
    with open(feedback_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except Exception:
                continue
    by_id = {}
    for e in entries:
        aid = e.get("arxiv_id")
        if not aid:
            continue
        stage = int(e.get("stage", 1))
        cur = by_id.setdefault(aid, {}).get(stage)
        if cur and cur.get("timestamp", "") > e.get("timestamp", ""):
            continue
        by_id[aid][stage] = e

    # Load metadata
    meta = {}
    if os.path.exists(metadata_path):
        with open(metadata_path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    m = json.loads(line)
                    if m.get("arxiv_id"):
                        meta[m["arxiv_id"]] = m
                except Exception:
                    continue

    cutoff = datetime.now() - timedelta(days=expiry_days)
    recycled = []
    for aid, stages in by_id.items():
        s1 = stages.get(1)
        s2 = stages.get(2)
        if not s1 or s2:
            continue
        if s1.get("rating", 0) < min_rating:
            continue
        try:
            ts = datetime.fromisoformat(s1["timestamp"])
            if ts >= cutoff:
                continue  # still within active queue window
        except Exception:
            continue
        m = meta.get(aid)
        if not m:
            continue
        paper = dict(m)
        paper["source"] = paper.get("source", "recycled")
        # If we already have scores, keep them; otherwise leave for rescoring.
        recycled.append(paper)
    return recycled


def load_or_refresh(interest, feedback_path, force=False, top_k=TOP_K):
    """Return cached classic papers if <30 days old, else refresh."""
    if not force and os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH) as f:
                cache = json.load(f)
            ts = datetime.fromisoformat(cache["timestamp"])
            age = (datetime.now() - ts).days
            if age < CACHE_TTL_DAYS:
                print(f"Using classics cache ({age} days old). Use --refresh-classics to force update.")
                return _filter_already_rated(cache["picks"], feedback_path)[:top_k]
        except Exception as e:
            print(f"Classics cache read failed ({e}), refreshing...")

    print("Refreshing classic papers...")
    metadata_path = os.path.join(os.path.dirname(feedback_path), "papers_metadata.jsonl")

    # Phase 0: pull expired queue papers (user's own backlog re-entering the pool)
    recycled = load_expired_queue_papers(feedback_path, metadata_path)
    print(f"  {len(recycled)} expired queue papers recycled into candidate pool")

    # Phase 1: seed papers + LLM generation
    seed_papers, _ = load_feedback_seeds(feedback_path)
    print(f"  {len(seed_papers)} high-rated seeds from feedback")
    candidates = llm_generate_classics(interest, seed_papers)

    # Phase 2: verify LLM candidates via arxiv
    print(f"  Verifying {len(candidates)} arxiv IDs ...")
    verified = verify_candidates(candidates)
    print(f"  {len(verified)} candidates verified on arxiv")

    # Carry over rank and reason from Claude's recommendations
    rank_map = {c["arxiv_id"]: c for c in candidates}
    for p in verified:
        meta = rank_map.get(p["arxiv_id"], {})
        p["rank"] = meta.get("rank", 999)
        if meta.get("reason"):
            p["Reasons for match"] = meta["reason"]

    # Phase 3: expand via Semantic Scholar
    if verified:
        top_seeds = verified[:5]
        expanded = expand_with_ss(top_seeds)
        seen = {p["arxiv_id"] for p in verified}
        for p in expanded:
            if p["arxiv_id"] not in seen:
                p["rank"] = 900  # SS expansions rank after Claude's picks
                verified.append(p)
                seen.add(p["arxiv_id"])

    # Phase 4: merge with recycled; dedupe
    all_candidates = []
    seen_ids = set()
    for p in recycled + verified:
        aid = p.get("arxiv_id")
        if not aid or aid in seen_ids:
            continue
        seen_ids.add(aid)
        all_candidates.append(p)

    # Phase 5: score with gpt-4o-mini — used only as a FILTER, not for ranking.
    # Claude Opus already ordered candidates by reading priority; we just need to
    # weed out clearly off-topic papers (core_score < MIN_FILTER_SCORE).
    from relevancy import generate_relevance_score
    MIN_FILTER_SCORE = 4
    need_scoring = [p for p in all_candidates if p.get("core_score") is None or p.get("transfer_score") is None]
    already_scored = [p for p in all_candidates if p.get("core_score") is not None and p.get("transfer_score") is not None]
    if need_scoring:
        newly_scored, _ = generate_relevance_score(
            need_scoring,
            query={"interest": interest},
            model_name="openai/gpt-4o-mini",
            num_paper_in_prompt=16,
        )
    else:
        newly_scored = []
    scored = already_scored + newly_scored

    # Phase 6: filter out clearly off-topic, then rank by Claude's reading order
    filtered = [
        p for p in scored
        if max(p.get("core_score", 0), p.get("transfer_score", 0)) >= MIN_FILTER_SCORE
    ]
    filtered.sort(key=lambda p: p.get("rank", 999))
    picks = filtered[:top_k * 2]

    with open(CACHE_PATH, "w") as f:
        json.dump(
            {"timestamp": datetime.now().isoformat(), "picks": picks},
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"Classics cache updated → {CACHE_PATH}")
    return _filter_already_rated(picks, feedback_path)[:top_k]


def _filter_already_rated(picks, feedback_path):
    _, rated_ids = load_feedback_seeds(feedback_path, min_rating=0)
    return [p for p in picks if p.get("arxiv_id", "") not in rated_ids]


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    fb = os.path.join(os.path.dirname(__file__), "..", "feedback.jsonl")
    picks = load_or_refresh("LLM agent system efficiency optimization", fb, force=True)
    print(f"\nTop {len(picks)} classics:")
    for p in picks:
        print(f"  [{p.get('core_score','?')}/{p.get('transfer_score','?')}] {p['title'][:90]}")
