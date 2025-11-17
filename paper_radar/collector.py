"""多源论文采集：OpenReview -> 官网 -> arXiv 级联。"""

import logging
from typing import Dict, List

import requests
from bs4 import BeautifulSoup

from paper_radar.arxiv_client import search_arxiv

logger = logging.getLogger(__name__)


def _normalize(paper: Dict, conference: str, year: int, source: str) -> Dict:
    paper.setdefault("affiliations", "")
    paper.setdefault("supplemental_url", paper.get("supplementary_material"))
    paper.update({"conference": conference, "year": year, "source": source})
    return paper


def fetch_openreview(conf) -> List[Dict]:
    if not conf.openreview or not conf.openreview.venue_id:
        return []
    url = "https://api.openreview.net/notes"
    params = {
        "venueid": conf.openreview.venue_id,
        "details": "replyCount",
        "limit": conf.openreview.limit or 200,
    }
    try:
        resp = requests.get(url, params=params, timeout=20)
        resp.raise_for_status()
        notes = resp.json().get("notes", [])
    except Exception as exc:
        logger.warning("OpenReview 获取失败 %s: %s", conf.name, exc)
        return []

    papers: List[Dict] = []
    for n in notes:
        content = n.get("content", {})
        author_ids = content.get("authorids") or []
        affiliations = fetch_openreview_affiliations(author_ids)
        papers.append(
            {
                "title": content.get("title", ""),
                "authors": ", ".join(content.get("authors", [])),
                "abstract": content.get("abstract", ""),
                "pdf_url": content.get("pdf"),
                "supplemental_url": content.get("supplementary_material"),
                "arxiv_id": None,
                "affiliations": "; ".join(affiliations),
                "keywords": ", ".join(content.get("keywords", [])),
            }
        )
    return papers


def fetch_official_site(conf) -> List[Dict]:
    site = conf.official_site
    if not site or not site.list_url:
        return []
    try:
        resp = requests.get(site.list_url, timeout=20)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("官网抓取失败 %s: %s", conf.name, exc)
        return []
    soup = BeautifulSoup(resp.text, "html.parser")
    items = soup.select(site.item_selector or "li")
    papers: List[Dict] = []
    for item in items:
        title_el = item.select_one(site.title_selector or "") if site.title_selector else item
        title = (title_el.get_text(" ", strip=True) if title_el else "").strip()
        if not title:
            continue
        authors = ""
        if site.authors_selector:
            authors_el = item.select_one(site.authors_selector)
            authors = authors_el.get_text(" ", strip=True) if authors_el else ""
        else:
            authors = getattr(item, "attrs", {}).get("data-authors", "")
        abstract = ""
        if site.abstract_selector:
            abstract_el = item.select_one(site.abstract_selector)
            abstract = abstract_el.get_text(" ", strip=True) if abstract_el else ""
        else:
            abstract = getattr(item, "attrs", {}).get("data-abstract", "")
        pdf_url = None
        if site.pdf_selector:
            pdf_link = item.select_one(site.pdf_selector)
            pdf_url = pdf_link.get("href") if pdf_link else None
        supp_url = None
        if site.supplemental_selector:
            supp_link = item.select_one(site.supplemental_selector)
            supp_url = supp_link.get("href") if supp_link else None
        affiliations = ""
        if site.affiliations_selector:
            aff_el = item.select_one(site.affiliations_selector)
            affiliations = aff_el.get_text(" ", strip=True) if aff_el else ""
        else:
            affiliations = getattr(item, "attrs", {}).get("data-affiliations", "")
        papers.append(
            {
                "title": title,
                "authors": authors,
                "affiliations": affiliations,
                "abstract": abstract,
                "pdf_url": pdf_url,
                "supplemental_url": supp_url,
                "arxiv_id": None,
                "keywords": ", ".join(conf.keywords or []),
            }
        )
    return papers


def collect_papers(conf, monitoring, categories: List[str], keywords: List[str]) -> List[Dict]:
    """按照优先级多源抓取并去重。"""

    priority = conf.source_priority or ["openreview", "official", "arxiv"]
    seen_titles = set()
    collected: List[Dict] = []

    for source in priority:
        papers: List[Dict] = []
        if source == "openreview":
            papers = fetch_openreview(conf)
        elif source == "official":
            papers = fetch_official_site(conf)
        elif source == "arxiv":
            papers = search_arxiv(
                conf.name,
                conf.year,
                categories,
                keywords,
                monitoring.arxiv_max_results,
                monitoring.arxiv_batch_days,
            )
        else:
            continue

        normalized = [_normalize(p, conf.name, conf.year, source) for p in papers]
        for p in normalized:
            title_key = p.get("title", "").lower()
            if title_key and title_key not in seen_titles:
                seen_titles.add(title_key)
                collected.append(p)

    return collected
def fetch_openreview_affiliations(author_ids):
    affs = []
    for aid in author_ids or []:
        try:
            resp = requests.get(
                "https://api.openreview.net/profiles", params={"id": aid}, timeout=10
            )
            resp.raise_for_status()
            profiles = resp.json().get("profiles", [])
            if not profiles:
                continue
            history = profiles[0].get("content", {}).get("history", [])
            if not history:
                continue
            latest = history[-1]
            inst = latest.get("institution")
            if isinstance(inst, dict):
                name = inst.get("name") or inst.get("domain")
            else:
                name = inst
            if name:
                affs.append(name)
        except Exception as exc:
            logger.debug("OpenReview 机构拉取失败 %s: %s", aid, exc)
    return affs
