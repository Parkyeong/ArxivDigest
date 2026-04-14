"""Small Flask server to receive paper ratings from digest.html.

Run: python feedback_server.py
Listens on http://127.0.0.1:5005
Appends each rating to ../feedback.jsonl (relative to this file).
"""
import json
import os
from datetime import datetime
from flask import Flask, request, jsonify

FEEDBACK_PATH = os.path.join(os.path.dirname(__file__), "..", "feedback.jsonl")

app = Flask(__name__)


@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.route("/rate", methods=["POST", "OPTIONS"])
def rate():
    if request.method == "OPTIONS":
        return ("", 204)
    data = request.get_json(force=True)
    arxiv_id = data.get("arxiv_id", "")
    title = data.get("title", "")
    rating = int(data.get("rating", 0))
    if not (1 <= rating <= 10) or not arxiv_id:
        return jsonify({"error": "invalid payload"}), 400

    entry = {
        "arxiv_id": arxiv_id,
        "title": title,
        "rating": rating,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    with open(FEEDBACK_PATH, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    total = sum(1 for _ in open(FEEDBACK_PATH))
    return jsonify({"ok": True, "total": total})


@app.route("/feedback", methods=["GET"])
def list_feedback():
    if not os.path.exists(FEEDBACK_PATH):
        return jsonify([])
    with open(FEEDBACK_PATH) as f:
        entries = [json.loads(l) for l in f if l.strip()]
    return jsonify(entries)


if __name__ == "__main__":
    print(f"Feedback server listening on http://127.0.0.1:5005")
    print(f"Writing to: {os.path.abspath(FEEDBACK_PATH)}")
    app.run(host="127.0.0.1", port=5005, debug=False)
