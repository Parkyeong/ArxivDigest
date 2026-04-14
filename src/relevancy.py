import json
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed

import tqdm
import utils


MAX_CONCURRENCY = 8


FEEDBACK_PATH = os.path.join(os.path.dirname(__file__), "..", "feedback.jsonl")
FEEDBACK_MIN = 5


def load_feedback_examples():
    """Return (positives, negatives) lists of {title, rating, reason} if enough feedback exists."""
    if not os.path.exists(FEEDBACK_PATH):
        return [], []
    entries = []
    with open(FEEDBACK_PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    if len(entries) < FEEDBACK_MIN:
        return [], []
    # dedupe by arxiv_id, keep latest rating
    seen = {}
    for e in entries:
        seen[e.get("arxiv_id", e.get("title"))] = e
    entries = list(seen.values())
    positives = sorted([e for e in entries if e["rating"] >= 7], key=lambda x: -x["rating"])[:5]
    negatives = sorted([e for e in entries if e["rating"] <= 4], key=lambda x: x["rating"])[:5]
    return positives, negatives


def encode_prompt(query, prompt_papers):
    prompt = open(os.path.join(os.path.dirname(__file__), "relevancy_prompt.txt")).read() + "\n"
    prompt += query['interest']

    positives, negatives = load_feedback_examples()
    if positives or negatives:
        prompt += "\n\n---\nUser feedback history (calibrate your scores to match these preferences):\n"
        if positives:
            prompt += "\nPapers the user RATED HIGH (these match the user's taste):\n"
            for e in positives:
                prompt += f"  - \"{e['title']}\" → user rating {e['rating']}/10\n"
        if negatives:
            prompt += "\nPapers the user RATED LOW (avoid recommending similar ones):\n"
            for e in negatives:
                prompt += f"  - \"{e['title']}\" → user rating {e['rating']}/10\n"
        prompt += "---\n"

    for idx, task_dict in enumerate(prompt_papers):
        (title, authors, abstract) = task_dict["title"], task_dict["authors"], task_dict["abstract"]
        if not title:
            raise RuntimeError("empty title")
        prompt += f"###\n"
        prompt += f"{idx + 1}. Title: {title}\n"
        prompt += f"{idx + 1}. Authors: {authors}\n"
        prompt += f"{idx + 1}. Abstract: {abstract}\n"
    prompt += f"\n Generate response:\n1."
    return prompt


def _extract_int(v):
    if isinstance(v, int):
        return v
    if isinstance(v, str):
        m = re.search(r"\d+", v)
        if m:
            return int(m.group())
    return 0


def post_process_chat_gpt_response(paper_data, response):
    """Parse dual-score JSON objects. Robust to markdown fences, numbered prefixes, pretty-printed JSON."""
    if response is None:
        return [], False
    content = response['message']['content']
    content = re.sub(r"```(?:json)?", "", content)

    # Find every top-level {...} block containing core_score. Non-greedy, multi-line.
    score_items = []
    for match in re.finditer(r"\{[^{}]*?core_score[^{}]*?\}", content, re.DOTALL):
        blob = match.group(0)
        # Normalize: remove stray newlines inside the JSON
        blob = re.sub(r"\s+", " ", blob)
        try:
            score_items.append(json.loads(blob))
        except Exception:
            # Try fixing common issues: trailing commas, single quotes
            fixed = blob.replace("'", '"')
            fixed = re.sub(r",\s*\}", "}", fixed)
            try:
                score_items.append(json.loads(fixed))
            except Exception:
                continue

    hallucination = len(score_items) != len(paper_data)
    if len(score_items) > len(paper_data):
        score_items = score_items[:len(paper_data)]

    results = []
    for idx, inst in enumerate(score_items):
        paper = dict(paper_data[idx])
        paper["core_score"] = _extract_int(inst.get("core_score", 0))
        paper["transfer_score"] = _extract_int(inst.get("transfer_score", 0))
        paper["Reasons for match"] = inst.get("Reasons for match") or inst.get("reasons for match", "")
        results.append(paper)
    return results, hallucination


def process_subject_fields(subjects):
    subjects = subjects.replace("Subjects:", "").strip()
    all_subjects = subjects.split(";")
    all_subjects = [s.split(" (")[0].strip() for s in all_subjects]
    return all_subjects


def _score_batch(prompt_papers, query, model_name, num_paper_in_prompt, temperature, top_p):
    prompt = encode_prompt(query, prompt_papers)
    decoding_args = utils.OpenAIDecodingArguments(
        temperature=temperature,
        n=1,
        max_tokens=160 * num_paper_in_prompt,
        top_p=top_p,
    )
    try:
        response = utils.openai_completion(
            prompts=prompt,
            model_name=model_name,
            batch_size=1,
            decoding_args=decoding_args,
        )
    except Exception as e:
        print(f"Batch failed: {e}")
        return [], False
    return post_process_chat_gpt_response(prompt_papers, response)


def generate_relevance_score(
    all_papers,
    query,
    model_name="gpt-4o-mini",
    num_paper_in_prompt=16,
    temperature=0.3,
    top_p=1.0,
):
    batches = [
        all_papers[i:i + num_paper_in_prompt]
        for i in range(0, len(all_papers), num_paper_in_prompt)
    ]

    ans_data = []
    hallucination = False
    with ThreadPoolExecutor(max_workers=MAX_CONCURRENCY) as pool:
        futures = [
            pool.submit(_score_batch, b, query, model_name, num_paper_in_prompt, temperature, top_p)
            for b in batches
        ]
        for fut in tqdm.tqdm(as_completed(futures), total=len(futures), desc="scoring"):
            batch_data, hallu = fut.result()
            hallucination = hallucination or hallu
            ans_data.extend(batch_data)

    return ans_data, hallucination
