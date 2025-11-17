import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

import yaml

from paper_radar.db import mark_conference_triggered, upsert_conference


CCF_DATA_FILE = "_data/conferences.yml"


def sync_ccf_repo(repo_dir: str):
    path = Path(repo_dir)
    if path.exists():
        subprocess.run(["git", "-C", str(path), "pull"], check=False)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "https://github.com/ccfddl/ccf-deadlines", str(path)], check=False)


def load_deadlines(repo_dir: str) -> Dict[str, str]:
    data_path = Path(repo_dir) / CCF_DATA_FILE
    if not data_path.exists():
        return {}
    with open(data_path, "r", encoding="utf-8") as f:
        confs = yaml.safe_load(f)
    # map acronym -> deadline
    result: Dict[str, str] = {}
    for conf in confs:
        acronym = conf.get("conf_name", "").upper()
        deadline = conf.get("deadline")
        if acronym and deadline:
            result[acronym] = deadline
    return result


def select_triggered_conferences(db_path: str, config_confs: List, deadlines: Dict[str, str], lag_days: int) -> List:
    triggered = []
    now = datetime.utcnow()
    for conf in config_confs:
        acronym = conf.name.upper()
        deadline_str = deadlines.get(acronym)
        upsert_conference(db_path, conf.name, conf.year, deadline=deadline_str)
        if not deadline_str:
            continue
        try:
            deadline_date = datetime.fromisoformat(deadline_str.replace("Z", "+00:00")).date()
        except Exception:
            continue
        if now.date() >= deadline_date + timedelta(days=lag_days):
            triggered.append(conf)
            mark_conference_triggered(db_path, conf.name, conf.year)
    return triggered
