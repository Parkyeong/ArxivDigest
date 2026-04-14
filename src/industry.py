"""Industry research tracker.

Fetches recent papers (last 14 days) from major AI labs, scores them with the
same dual-score LLM pipeline, and returns the top 3 per lab.

Sources:
  - arXiv API: DeepMind, Meta FAIR, Microsoft Research, DeepSeek, Qwen
  - HTML scrape: OpenAI, Anthropic
"""
import json
import os
import re
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "industry_cache.json")
CACHE_TTL_DAYS = 7
WINDOW_DAYS = 14
TOP_K_PER_LAB = 3
MIN_SCORE = 5

LABS = {
    "Google DeepMind": {
        "source": "arxiv",
        "query": '("Google DeepMind" OR "DeepMind")',
        "strict_author": False,
    },
    "Meta FAIR": {
        "source": "arxiv",
        "query": '("Meta AI" OR "FAIR at Meta" OR "Meta Superintelligence")',
        "strict_author": False,
    },
    "Microsoft Research": {
        "source": "arxiv",
        "query": '("Microsoft Research" OR "Microsoft AI")',
        "strict_author": False,
    },
    "OpenAI": {
        "source": "sitemap",
        "sitemap_url": "https://openai.com/sitemap.xml",
        "path_prefix": "/index/",
    },
    "Anthropic": {
        "source": "sitemap",
        "sitemap_url": "https://www.anthropic.com/sitemap.xml",
        "path_prefix": "/research/",
    },
}


def fetch_arxiv(query, days=WINDOW_DAYS, max_results=80,
                author_keywords=None, strict_author=False):
    """Query arXiv API. If strict_author, keep only papers whose author list matches one of author_keywords."""
    import urllib.parse
    import urllib.request

    # If caller already specified a field prefix (au:, ti:, abs:), use as-is. Otherwise default to all:.
    if re.match(r"^(au|ti|abs|all|cat):", query.strip()):
        search_query = urllib.parse.quote(query)
    else:
        search_query = urllib.parse.quote(f"all:{query}")
    url = (
        f"http://export.arxiv.org/api/query?search_query={search_query}"
        f"&sortBy=submittedDate&sortOrder=descending&max_results={max_results}"
    )
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            xml = resp.read().decode("utf-8")
    except Exception as e:
        print(f"  arXiv fetch failed for {query}: {e}")
        return []

    soup = BeautifulSoup(xml, features="xml")
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    results = []
    for entry in soup.find_all("entry"):
        published = entry.find("published")
        if not published:
            continue
        pub_dt = datetime.fromisoformat(published.text.replace("Z", "+00:00"))
        if pub_dt < cutoff:
            continue
        title = re.sub(r"\s+", " ", entry.find("title").text).strip()
        abstract = re.sub(r"\s+", " ", entry.find("summary").text).strip()
        authors = ", ".join(a.find("name").text for a in entry.find_all("author"))
        arxiv_id = entry.find("id").text.rsplit("/", 1)[-1].split("v")[0]

        if strict_author and author_keywords:
            authors_lower = authors.lower()
            if not any(kw.lower() in authors_lower for kw in author_keywords):
                continue

        results.append({
            "title": title,
            "authors": authors,
            "abstract": abstract,
            "main_page": f"https://arxiv.org/abs/{arxiv_id}",
            "published": pub_dt.isoformat(),
        })
    return results


def _clean_page_title(raw):
    """Strip leading dates, category tags, and trailing site names from scraped <title>."""
    if not raw:
        return ""
    t = re.sub(r"\s+", " ", raw).strip()
    for sep in [" \\ ", " | ", " - ", " — "]:
        for suffix in ["Anthropic", "OpenAI", "OpenAI Blog"]:
            if t.endswith(sep + suffix):
                t = t[: -len(sep + suffix)]
    t = re.sub(r"^\w{3,9}\s+\d{1,2},?\s+\d{4}\s+", "", t)
    t = re.sub(r"^(Interpretability|Alignment|Safety|Research|Policy|Society|Product)\s+", "", t)
    return t.strip()


def _fetch_xml(url):
    try:
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; arxiv-digest/1.0)"},
            timeout=15,
        )
        resp.raise_for_status()
        return BeautifulSoup(resp.text, features="xml")
    except Exception as e:
        print(f"  fetch failed for {url}: {e}")
        return None


def fetch_sitemap(sitemap_url, path_prefix, days=WINDOW_DAYS, max_pages=30):
    """Parse sitemap.xml (handling sitemap-index recursion), filter URLs under path_prefix, fetch each page for title + description."""
    soup = _fetch_xml(sitemap_url)
    if soup is None:
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # If this is a sitemap index, recurse into child sitemaps that match the prefix
    sub_sitemaps = soup.find_all("sitemap")
    if sub_sitemaps:
        urls_to_scan = []
        for sm in sub_sitemaps:
            loc = sm.find("loc")
            if loc and (path_prefix.strip("/") in loc.text or "research" in loc.text or "news" in loc.text or "page" in loc.text):
                urls_to_scan.append(loc.text)
        all_candidates = []
        for sub in urls_to_scan:
            sub_soup = _fetch_xml(sub)
            if sub_soup is None:
                continue
            for url_tag in sub_soup.find_all("url"):
                loc = url_tag.find("loc")
                lastmod = url_tag.find("lastmod")
                if not loc or path_prefix not in loc.text:
                    continue
                if lastmod:
                    try:
                        mod_dt = datetime.fromisoformat(lastmod.text.replace("Z", "+00:00"))
                        if mod_dt < cutoff:
                            continue
                    except Exception:
                        pass
                all_candidates.append((loc.text, lastmod.text if lastmod else ""))
        candidates = all_candidates
    else:
        candidates = []
        for url_tag in soup.find_all("url"):
            loc = url_tag.find("loc")
            lastmod = url_tag.find("lastmod")
            if not loc or path_prefix not in loc.text:
                continue
            if lastmod:
                try:
                    mod_dt = datetime.fromisoformat(lastmod.text.replace("Z", "+00:00"))
                    if mod_dt < cutoff:
                        continue
                except Exception:
                    pass
            candidates.append((loc.text, lastmod.text if lastmod else ""))

    candidates.sort(key=lambda x: x[1], reverse=True)
    candidates = candidates[:max_pages]

    results = []
    for page_url, mod in candidates:
        try:
            r = requests.get(
                page_url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; arxiv-digest/1.0)"},
                timeout=10,
            )
            page = BeautifulSoup(r.text, features="html.parser")
            title_tag = page.find("meta", property="og:title") or page.find("title")
            if title_tag and title_tag.has_attr("content"):
                title = title_tag["content"]
            elif title_tag:
                title = title_tag.text
            else:
                title = ""
            title = _clean_page_title(title)

            desc_tag = page.find("meta", property="og:description") or page.find("meta", {"name": "description"})
            abstract = desc_tag["content"] if desc_tag and desc_tag.has_attr("content") else ""
            abstract = re.sub(r"\s+", " ", abstract).strip() or title

            if not title or len(title) < 10:
                continue
            results.append({
                "title": title,
                "authors": "",
                "abstract": abstract,
                "main_page": page_url,
                "published": mod,
            })
        except Exception:
            continue
    return results


def collect_industry_papers():
    print("Fetching industry papers...")
    all_papers = []
    for lab, cfg in LABS.items():
        print(f"  {lab} ...", end=" ", flush=True)
        if cfg["source"] == "arxiv":
            papers = fetch_arxiv(
                cfg["query"],
                author_keywords=cfg.get("author_keywords"),
                strict_author=cfg.get("strict_author", False),
            )
        elif cfg["source"] == "sitemap":
            papers = fetch_sitemap(cfg["sitemap_url"], cfg["path_prefix"])
        else:
            papers = []
        print(f"{len(papers)} papers")
        for p in papers:
            p["lab"] = lab
        all_papers.extend(papers)
    return all_papers


def score_and_pick(all_papers, interest, model_name="gpt-4o-mini"):
    """Score with existing pipeline and pick top-k per lab by max(core, transfer)."""
    from relevancy import generate_relevance_score

    if not all_papers:
        return {}

    scored, _ = generate_relevance_score(
        all_papers,
        query={"interest": interest},
        model_name=model_name,
        num_paper_in_prompt=16,
    )

    by_lab = {}
    for p in scored:
        by_lab.setdefault(p.get("lab", "Unknown"), []).append(p)

    picks = {}
    for lab, papers in by_lab.items():
        qualified = [
            p for p in papers
            if max(p.get("core_score", 0), p.get("transfer_score", 0)) >= MIN_SCORE
        ]
        qualified.sort(
            key=lambda p: max(p.get("core_score", 0), p.get("transfer_score", 0)),
            reverse=True,
        )
        picks[lab] = qualified[:TOP_K_PER_LAB]
    return picks


def load_or_refresh(interest, force=False):
    """Return cached picks if <7 days old, else refresh."""
    if not force and os.path.exists(CACHE_PATH):
        try:
            with open(CACHE_PATH) as f:
                cache = json.load(f)
            ts = datetime.fromisoformat(cache["timestamp"])
            age = (datetime.now() - ts).days
            if age < CACHE_TTL_DAYS:
                print(f"Using industry cache ({age} days old). Use --refresh-industry to force update.")
                return cache["picks"]
        except Exception as e:
            print(f"Cache read failed ({e}), refreshing...")

    raw = collect_industry_papers()
    picks = score_and_pick(raw, interest)
    with open(CACHE_PATH, "w") as f:
        json.dump(
            {"timestamp": datetime.now().isoformat(), "picks": picks},
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"Industry cache updated → {CACHE_PATH}")
    return picks


if __name__ == "__main__":
    # Quick test
    from dotenv import load_dotenv
    load_dotenv()
    picks = load_or_refresh("LLM agent systems efficiency", force=True)
    for lab, papers in picks.items():
        print(f"\n=== {lab} ({len(papers)}) ===")
        for p in papers:
            print(f"  [{p['core_score']}/{p['transfer_score']}] {p['title'][:80]}")
