import datetime as dt
import logging
import re
from typing import Dict, List

import feedparser

logger = logging.getLogger(__name__)


ARXIV_API = "http://export.arxiv.org/api/query"


def build_query(conf_name: str, year: int, categories: List[str], keywords: List[str]) -> str:
    base_terms = [f"abs:\"{conf_name} {year}\"", f"title:\"{conf_name} {year}\""]
    category_filter = " OR ".join([f"cat:{c}" for c in categories])
    keyword_filter = " OR ".join([f"abs:\"{kw}\"" for kw in keywords]) if keywords else ""
    parts = ["(" + " OR ".join(base_terms) + ")"]
    if category_filter:
        parts.append(f"({category_filter})")
    if keyword_filter:
        parts.append(f"({keyword_filter})")
    return " AND ".join(parts)


def search_arxiv(conf_name: str, year: int, categories: List[str], keywords: List[str], max_results: int, days: int) -> List[Dict]:
    query = build_query(conf_name, year, categories, keywords)
    start_date = (dt.datetime.utcnow() - dt.timedelta(days=days)).strftime("%Y%m%d")
    url = (
        f"{ARXIV_API}?search_query=({query})"
        f"&sortBy=submittedDate&sortOrder=descending&max_results={max_results}"
    )
    logger.info("调用 arXiv API: %s", url)
    feed = feedparser.parse(url)
    papers: List[Dict] = []
    for entry in feed.entries:
        submitted = entry.get("published")
        if submitted and submitted[:10].replace("-", "") < start_date:
            continue
        affiliations = []
        for author in entry.get("authors", []):
            aff = None
            if isinstance(author, dict):
                aff = author.get("affiliation") or author.get("affil")
            else:
                aff = getattr(author, "affiliation", None)
            if aff:
                if isinstance(aff, list):
                    affiliations.extend([a for a in aff if a])
                else:
                    affiliations.append(aff)
        supplemental = None
        for link in entry.get("links", []):
            rel = getattr(link, "rel", None) or link.get("rel") if isinstance(link, dict) else None
            title = getattr(link, "title", None) or link.get("title") if isinstance(link, dict) else None
            if rel == "related" or (title and "supp" in title.lower()):
                supplemental = getattr(link, "href", None) or link.get("href")
                break
            if title and title.lower() == "doi":
                supplemental = getattr(link, "href", None) or link.get("href")
        pdf_url = next(
            (
                getattr(l, "href", None) or l.get("href")
                for l in entry.get("links", [])
                if getattr(l, "rel", None) == "alternate"
                or getattr(l, "type", None) == "application/pdf"
                or (isinstance(l, dict) and (l.get("rel") == "alternate" or l.get("type") == "application/pdf"))
            ),
            None,
        )
        paper = {
            "title": entry.get("title", "").replace("\n", " "),
            "authors": ", ".join(a.get("name") for a in entry.get("authors", [])),
            "abstract": entry.get("summary", ""),
            "pdf_url": pdf_url,
            "arxiv_id": entry.get("id", "").split("/abs/")[-1],
            "keywords": ", ".join(keywords),
            "affiliations": "; ".join(dict.fromkeys(affiliations)),
            "supplemental_url": supplemental,
            "source": "arxiv",
        }
        papers.append(paper)
    return papers


def extract_github_links(text: str) -> List[str]:
    if not text:
        return []
    pattern = r"https?://github\.com/[\w\-\.]+/[\w\-\.]+"
    return list({m.group(0) for m in re.finditer(pattern, text)})
