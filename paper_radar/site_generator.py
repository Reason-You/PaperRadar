import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

from jinja2 import Environment, FileSystemLoader, select_autoescape

from paper_radar import db


def build_env(template_dir: str):
    return Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(['html']),
    )


def generate_site(db_path: str, site_dir: str, template_dir: str, site_meta: Dict):
    Path(site_dir).mkdir(parents=True, exist_ok=True)
    env = build_env(template_dir)
    conferences = db.list_conferences(db_path)
    index_tmpl = env.get_template('index.html')
    (Path(site_dir) / 'index.html').write_text(
        index_tmpl.render(conferences=conferences, site=site_meta), encoding='utf-8'
    )
    conf_tmpl = env.get_template('conference.html')
    for conf in conferences:
        papers = db.fetch_papers(db_path, conf['name'], conf['year'])
        paper_map = {p['id']: p for p in papers}
        summaries = {p['id']: None for p in papers}
        with db.get_conn(db_path) as conn:
            cur = conn.execute(
                "SELECT paper_id, tldr_en, tldr_zh FROM summaries WHERE paper_id IN (%s)" %
                ",".join(str(pid) for pid in paper_map.keys()) if paper_map else "SELECT paper_id, tldr_en, tldr_zh FROM summaries WHERE 1=0"
            )
            for row in cur.fetchall():
                summaries[row[0]] = {"tldr_en": row[1], "tldr_zh": row[2]}
            cluster_cur = conn.execute(
                "SELECT paper_id, label FROM clusters WHERE conference=? AND year=?",
                (conf['name'], conf['year']),
            )
            clusters = defaultdict(list)
            cluster_counts = defaultdict(int)
            for pid, label in cluster_cur.fetchall():
                clusters[pid].append(label)
                cluster_counts[label] += 1
            trend_cur = conn.execute(
                "SELECT summary FROM trends WHERE conference=? AND year=?",
                (conf['name'], conf['year']),
            )
            trend_row = trend_cur.fetchone()
            trend_summary = trend_row[0] if trend_row else "尚未生成趋势分析"
            code_map = defaultdict(list)
            code_cur = conn.execute(
                "SELECT paper_id, url, status, last_commit, has_readme, has_code FROM code_links WHERE paper_id IN (%s)" %
                ",".join(str(pid) for pid in paper_map.keys()) if paper_map else "SELECT paper_id, url, status, last_commit, has_readme, has_code FROM code_links WHERE 1=0"
            )
            for row in code_cur.fetchall():
                code_map[row[0]].append(
                    {
                        "url": row[1],
                        "status": row[2],
                        "last_commit": row[3],
                        "has_readme": bool(row[4]),
                        "has_code": bool(row[5]),
                    }
                )
        output = conf_tmpl.render(
            conf=conf,
            papers=papers,
            summaries=summaries,
            clusters=clusters,
            cluster_counts=json.dumps(cluster_counts, ensure_ascii=False),
            trend_summary=trend_summary,
            code_map=code_map,
            site=site_meta,
        )
        filename = f"{conf['name']}_{conf['year']}.html"
        (Path(site_dir) / filename).write_text(output, encoding='utf-8')
