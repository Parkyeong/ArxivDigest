"""Flask server for the two-stage reading pipeline.

Stage 1 = quick scan rating on daily digest (rating ≥7 → reading queue)
Stage 2 = post-read rating on queue page (rating ≥7 → library)

Endpoints:
  POST /rate      — submit a rating (stage 1 or 2) + optional comment + paper metadata
  GET  /ratings   — return {arxiv_id: {stage_1?: {...}, stage_2?: {...}}}
  GET  /queue     — return reading queue entries (stage-1 ≥7, no stage-2, not expired)
  GET  /library   — return library entries (stage-2 ≥7); supports ?q=<search>
"""
import json
import os
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

ROOT = os.path.join(os.path.dirname(__file__), "..")
FEEDBACK_PATH = os.path.join(ROOT, "feedback.jsonl")
METADATA_PATH = os.path.join(ROOT, "papers_metadata.jsonl")
QUEUE_EXPIRY_DAYS = 30
LIBRARY_MIN_RATING = 7
QUEUE_MIN_RATING = 7

app = Flask(__name__)


@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


def _read_jsonl(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    return out


def _latest_metadata():
    """Return {arxiv_id: metadata_dict} for all known papers (latest upsert wins)."""
    meta = {}
    for entry in _read_jsonl(METADATA_PATH):
        aid = entry.get("arxiv_id")
        if aid:
            meta[aid] = entry
    return meta


def _upsert_metadata(paper):
    """Append metadata entry (deduped by last-write-wins in _latest_metadata)."""
    if not paper or not paper.get("arxiv_id"):
        return
    with open(METADATA_PATH, "a") as f:
        f.write(json.dumps(paper, ensure_ascii=False) + "\n")


def _latest_ratings_by_stage():
    """Return {arxiv_id: {1: {rating, comment, timestamp}, 2: {...}}} (latest per stage)."""
    out = {}
    for e in _read_jsonl(FEEDBACK_PATH):
        aid = e.get("arxiv_id")
        if not aid:
            continue
        stage = int(e.get("stage", 1))
        if stage not in (1, 2):
            continue
        # keep latest by timestamp
        existing = out.setdefault(aid, {}).get(stage)
        if existing and existing.get("timestamp", "") > e.get("timestamp", ""):
            continue
        out[aid][stage] = {
            "rating": e.get("rating"),
            "comment": e.get("comment", ""),
            "timestamp": e.get("timestamp", ""),
        }
    return out


@app.route("/rate", methods=["POST", "OPTIONS"])
def rate():
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(force=True)
    arxiv_id = str(data.get("arxiv_id", "")).strip()
    rating = int(data.get("rating", 0))
    stage = int(data.get("stage", 1))
    comment = (data.get("comment") or "").strip()
    metadata = data.get("metadata")  # optional full paper dict

    if not (1 <= rating <= 10) or not arxiv_id or stage not in (1, 2):
        return jsonify({"error": "invalid payload"}), 400

    entry = {
        "arxiv_id": arxiv_id,
        "title": data.get("title", ""),
        "rating": rating,
        "stage": stage,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    if comment:
        entry["comment"] = comment

    with open(FEEDBACK_PATH, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    if metadata and isinstance(metadata, dict):
        metadata["arxiv_id"] = arxiv_id
        _upsert_metadata(metadata)

    total = len(_read_jsonl(FEEDBACK_PATH))
    return jsonify({"ok": True, "total": total, "stage": stage})


@app.route("/ratings", methods=["GET"])
def ratings():
    """For UI state restore on page reload."""
    return jsonify(_latest_ratings_by_stage())


@app.route("/queue", methods=["GET"])
def queue():
    """Reading queue: stage-1 ≥7, not yet stage-2, not expired >30d."""
    meta = _latest_metadata()
    ratings_by = _latest_ratings_by_stage()
    cutoff = datetime.now() - timedelta(days=QUEUE_EXPIRY_DAYS)
    out = []
    for aid, stages in ratings_by.items():
        s1 = stages.get(1)
        s2 = stages.get(2)
        if not s1 or s1.get("rating", 0) < QUEUE_MIN_RATING:
            continue
        if s2:  # already progressed to library pipeline
            continue
        try:
            ts = datetime.fromisoformat(s1["timestamp"])
            if ts < cutoff:
                continue  # expired — will be recycled to classics
        except Exception:
            pass
        paper = meta.get(aid, {})
        out.append({
            "arxiv_id": aid,
            "title": paper.get("title") or s1.get("title", ""),
            "authors": paper.get("authors", ""),
            "abstract": paper.get("abstract", ""),
            "main_page": paper.get("main_page", f"https://arxiv.org/abs/{aid}"),
            "core_score": paper.get("core_score"),
            "transfer_score": paper.get("transfer_score"),
            "reason": paper.get("reason") or paper.get("Reasons for match", ""),
            "source": paper.get("source", "unknown"),
            "stage_1_rating": s1.get("rating"),
            "stage_1_comment": s1.get("comment", ""),
            "stage_1_timestamp": s1.get("timestamp"),
        })
    out.sort(key=lambda p: (p.get("stage_1_rating") or 0), reverse=True)
    return jsonify(out)


@app.route("/library", methods=["GET"])
def library():
    """Library: stage-2 ≥7, optional ?q= search on title/abstract."""
    q = (request.args.get("q") or "").strip().lower()
    meta = _latest_metadata()
    ratings_by = _latest_ratings_by_stage()
    out = []
    for aid, stages in ratings_by.items():
        s2 = stages.get(2)
        if not s2 or s2.get("rating", 0) < LIBRARY_MIN_RATING:
            continue
        paper = meta.get(aid, {})
        title = paper.get("title", "")
        abstract = paper.get("abstract", "")
        entry = {
            "arxiv_id": aid,
            "title": title,
            "authors": paper.get("authors", ""),
            "abstract": abstract,
            "main_page": paper.get("main_page", f"https://arxiv.org/abs/{aid}" if aid and not aid.startswith("seed") else ""),
            "core_score": paper.get("core_score"),
            "transfer_score": paper.get("transfer_score"),
            "source": paper.get("source", "unknown"),
            "stage_2_rating": s2.get("rating"),
            "stage_2_comment": s2.get("comment", ""),
            "stage_2_timestamp": s2.get("timestamp"),
            "note": paper.get("note", ""),
        }
        if q:
            hay = (title + " " + abstract + " " + entry["note"]).lower()
            if q not in hay:
                continue
        out.append(entry)
    out.sort(key=lambda p: (p.get("stage_2_rating") or 0, p.get("stage_2_timestamp") or ""), reverse=True)
    return jsonify(out)


@app.route("/feedback", methods=["GET"])
def list_feedback():
    return jsonify(_read_jsonl(FEEDBACK_PATH))


if __name__ == "__main__":
    print("Feedback server listening on http://127.0.0.1:5005")
    print(f"Feedback  → {os.path.abspath(FEEDBACK_PATH)}")
    print(f"Metadata  → {os.path.abspath(METADATA_PATH)}")
    app.run(host="127.0.0.1", port=5005, debug=False)
