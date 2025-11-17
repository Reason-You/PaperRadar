import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, Iterable, List, Optional, Tuple

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS conferences (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        year INTEGER NOT NULL,
        deadline DATE,
        triggered_at DATETIME,
        UNIQUE(name, year)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS papers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conference TEXT NOT NULL,
        year INTEGER NOT NULL,
        source TEXT,
        title TEXT NOT NULL,
        authors TEXT,
        affiliations TEXT,
        abstract TEXT,
        pdf_url TEXT,
        supplemental_url TEXT,
        arxiv_id TEXT,
        keywords TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(conference, year, arxiv_id, title)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS summaries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paper_id INTEGER NOT NULL,
        tldr_en TEXT,
        tldr_zh TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(paper_id) REFERENCES papers(id) ON DELETE CASCADE,
        UNIQUE(paper_id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS clusters (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conference TEXT NOT NULL,
        year INTEGER NOT NULL,
        label TEXT NOT NULL,
        paper_id INTEGER NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(paper_id) REFERENCES papers(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS trends (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        conference TEXT NOT NULL,
        year INTEGER NOT NULL,
        summary TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(conference, year)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS code_links (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        paper_id INTEGER NOT NULL,
        url TEXT NOT NULL,
        status TEXT NOT NULL,
        last_commit TEXT,
        has_readme INTEGER,
        has_code INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(paper_id) REFERENCES papers(id) ON DELETE CASCADE,
        UNIQUE(paper_id, url)
    );
    """,
]


@contextmanager
def get_conn(db_path: str):
    conn = sqlite3.connect(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(db_path: str):
    with get_conn(db_path) as conn:
        cur = conn.cursor()
        for stmt in SCHEMA:
            cur.executescript(stmt)


def upsert_conference(db_path: str, name: str, year: int, deadline: Optional[str] = None):
    with get_conn(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO conferences (name, year, deadline) VALUES (?, ?, ?)",
            (name, year, deadline),
        )


def insert_papers(db_path: str, records: List[Dict]):
    with get_conn(db_path) as conn:
        for rec in records:
            conn.execute(
                """
                INSERT OR IGNORE INTO papers (
                    conference, year, source, title, authors, affiliations, abstract,
                    pdf_url, supplemental_url, arxiv_id, keywords
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rec.get("conference"),
                    rec.get("year"),
                    rec.get("source"),
                    rec.get("title"),
                    rec.get("authors"),
                    rec.get("affiliations"),
                    rec.get("abstract"),
                    rec.get("pdf_url"),
                    rec.get("supplemental_url"),
                    rec.get("arxiv_id"),
                    rec.get("keywords"),
                ),
            )


def fetch_papers_without_summary(db_path: str, conference: str, year: int, limit: int) -> List[Tuple]:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """
            SELECT p.id, p.title, p.abstract
            FROM papers p
            LEFT JOIN summaries s ON p.id = s.paper_id
            WHERE p.conference=? AND p.year=? AND s.id IS NULL AND p.abstract IS NOT NULL
            LIMIT ?
            """,
            (conference, year, limit),
        )
        return cur.fetchall()


def save_summaries(db_path: str, summaries: List[Tuple[int, str, str]]):
    with get_conn(db_path) as conn:
        for paper_id, tldr_en, tldr_zh in summaries:
            conn.execute(
                "INSERT OR REPLACE INTO summaries (paper_id, tldr_en, tldr_zh) VALUES (?, ?, ?)",
                (paper_id, tldr_en, tldr_zh),
            )


def save_clusters(db_path: str, conference: str, year: int, assignments: List[Tuple[int, str]]):
    with get_conn(db_path) as conn:
        conn.execute("DELETE FROM clusters WHERE conference=? AND year=?", (conference, year))
        for paper_id, label in assignments:
            conn.execute(
                "INSERT INTO clusters (conference, year, label, paper_id) VALUES (?, ?, ?, ?)",
                (conference, year, label, paper_id),
            )


def save_trend(db_path: str, conference: str, year: int, summary: str):
    with get_conn(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO trends (conference, year, summary) VALUES (?, ?, ?)",
            (conference, year, summary),
        )


def fetch_papers(db_path: str, conference: str, year: int) -> List[Dict]:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """
            SELECT id, title, authors, affiliations, abstract, pdf_url, supplemental_url, arxiv_id, keywords, created_at
            FROM papers WHERE conference=? AND year=?
            """,
            (conference, year),
        )
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def save_code_link(db_path: str, paper_id: int, url: str, status: str, last_commit: Optional[str], has_readme: bool, has_code: bool):
    with get_conn(db_path) as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO code_links (paper_id, url, status, last_commit, has_readme, has_code)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (paper_id, url, status, last_commit, int(has_readme), int(has_code)),
        )


def fetch_code_links(db_path: str, paper_id: int) -> List[Dict]:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            "SELECT url, status, last_commit, has_readme, has_code FROM code_links WHERE paper_id=?",
            (paper_id,),
        )
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def fetch_cluster_counts(db_path: str, conference: str, year: int) -> List[Tuple[str, int]]:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            "SELECT label, COUNT(*) FROM clusters WHERE conference=? AND year=? GROUP BY label",
            (conference, year),
        )
        return cur.fetchall()


def mark_conference_triggered(db_path: str, name: str, year: int):
    with get_conn(db_path) as conn:
        conn.execute(
            "UPDATE conferences SET triggered_at=? WHERE name=? AND year=?",
            (datetime.utcnow().isoformat(), name, year),
        )


def list_conferences(db_path: str) -> List[Dict]:
    with get_conn(db_path) as conn:
        cur = conn.execute(
            "SELECT name, year, deadline, triggered_at FROM conferences ORDER BY year DESC, name ASC"
        )
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
