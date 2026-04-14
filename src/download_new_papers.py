# encoding: utf-8
import os
import tqdm
from bs4 import BeautifulSoup as bs
import urllib.request
import json
import datetime
import pytz
import re


def _clean(text, prefix):
    """Strip a prefix like 'Title:' regardless of what whitespace follows."""
    text = re.sub(r"\s+", " ", text).strip()
    if text.lower().startswith(prefix.lower()):
        text = text[len(prefix):].strip()
    return text


def _download_new_papers(field_abbr):
    NEW_SUB_URL = f'https://arxiv.org/list/{field_abbr}/new'
    page = urllib.request.urlopen(NEW_SUB_URL)
    soup = bs(page, features="html.parser")
    content = soup.body.find("div", {'id': 'content'})

    dt_list = content.dl.find_all("dt")
    dd_list = content.dl.find_all("dd")
    arxiv_base = "https://arxiv.org/abs/"

    assert len(dt_list) == len(dd_list)
    new_paper_list = []
    for i in tqdm.tqdm(range(len(dt_list))):
        paper = {}
        # Extract arxiv id from the abs link inside dt
        link = dt_list[i].find("a", href=re.compile(r"/abs/"))
        if link:
            paper_number = link["href"].rsplit("/", 1)[-1]
        else:
            # fallback: regex on dt text
            m = re.search(r"(\d{4}\.\d{4,5})", dt_list[i].text)
            paper_number = m.group(1) if m else ""
        if not paper_number:
            continue
        paper['main_page'] = arxiv_base + paper_number
        paper['pdf'] = f"https://arxiv.org/pdf/{paper_number}"

        paper['title'] = _clean(
            dd_list[i].find("div", {"class": "list-title mathjax"}).text, "Title:"
        )
        paper['authors'] = _clean(
            dd_list[i].find("div", {"class": "list-authors"}).text, "Authors:"
        )
        paper['subjects'] = _clean(
            dd_list[i].find("div", {"class": "list-subjects"}).text, "Subjects:"
        )
        paper['abstract'] = re.sub(
            r"\s+", " ",
            dd_list[i].find("p", {"class": "mathjax"}).text,
        ).strip()
        new_paper_list.append(paper)


    #  check if ./data exist, if not, create it
    if not os.path.exists("./data"):
        os.makedirs("./data")

    # save new_paper_list to a jsonl file, with each line as the element of a dictionary
    date = datetime.date.fromtimestamp(datetime.datetime.now(tz=pytz.timezone("America/New_York")).timestamp())
    date = date.strftime("%a, %d %b %y")
    with open(f"./data/{field_abbr}_{date}.jsonl", "w") as f:
        for paper in new_paper_list:
            f.write(json.dumps(paper) + "\n")


def get_papers(field_abbr, limit=None):
    date = datetime.date.fromtimestamp(datetime.datetime.now(tz=pytz.timezone("America/New_York")).timestamp())
    date = date.strftime("%a, %d %b %y")
    if not os.path.exists(f"./data/{field_abbr}_{date}.jsonl"):
        _download_new_papers(field_abbr)
    results = []
    with open(f"./data/{field_abbr}_{date}.jsonl", "r") as f:
        for i, line in enumerate(f.readlines()):
            if limit and i == limit:
                return results
            results.append(json.loads(line))
    return results
