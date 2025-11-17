import logging
from datetime import datetime
from typing import Optional

import requests

from paper_radar.llm_mcp import LLMClient, ToolSpec

logger = logging.getLogger(__name__)
GITHUB_API = "https://api.github.com"


def _get_headers(token: Optional[str]):
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_repo_metadata(url: str, token: Optional[str]):
    parts = url.rstrip("/").split("github.com/")[-1].split("/")
    owner, repo = parts[0], parts[1]
    resp = requests.get(f"{GITHUB_API}/repos/{owner}/{repo}", headers=_get_headers(token), timeout=10)
    if resp.status_code != 200:
        logger.warning("GitHub API 获取失败 %s -> %s", url, resp.status_code)
        return None
    return resp.json()


def fetch_latest_commit_date(owner: str, repo: str, token: Optional[str]) -> Optional[str]:
    resp = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/commits",
        headers=_get_headers(token),
        params={"per_page": 1},
        timeout=10,
    )
    if resp.status_code != 200:
        return None
    items = resp.json()
    if not items:
        return None
    return items[0].get("commit", {}).get("author", {}).get("date")


def fetch_readme(owner: str, repo: str, token: Optional[str]) -> str:
    resp = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/readme",
        headers=_get_headers(token),
        timeout=10,
    )
    if resp.status_code != 200:
        return ""
    content = resp.json().get("content", "")
    import base64

    try:
        return base64.b64decode(content).decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _check_code_files(owner: str, repo: str, token: Optional[str]) -> bool:
    resp = requests.get(
        f"{GITHUB_API}/repos/{owner}/{repo}/contents",
        headers=_get_headers(token),
        timeout=10,
    )
    if resp.status_code != 200:
        return False
    data = resp.json()
    allowed_ext = {".py", ".ipynb", ".cc", ".cpp", ".cu", ".js", ".java"}
    for item in data:
        name = item.get("name", "").lower()
        if any(name.endswith(ext) for ext in allowed_ext):
            return True
    return False


def verify_repo(url: str, token: Optional[str], llm: Optional[LLMClient], paper_date: Optional[str]):
    meta = fetch_repo_metadata(url, token)
    if not meta:
        return {
            "status": "None",
            "has_readme": False,
            "has_code": False,
            "last_commit": None,
        }
    owner, repo = url.rstrip("/").split("github.com/")[-1].split("/")[:2]
    has_readme = meta.get("size", 0) > 0
    last_commit = fetch_latest_commit_date(owner, repo, token) or meta.get("pushed_at")
    has_code = _check_code_files(owner, repo, token)
    status = "Verified" if has_code and has_readme else "Placeholder"

    if paper_date and last_commit:
        try:
            paper_dt = datetime.fromisoformat(paper_date.replace("Z", "+00:00"))
            repo_dt = datetime.fromisoformat(last_commit.replace("Z", "+00:00"))
            if abs((repo_dt - paper_dt).days) > 180:
                status = "Placeholder"
        except Exception:
            pass

    readme_text = ""
    try:
        readme_text = fetch_readme(owner, repo, token)
    except Exception:
        readme_text = ""
    if llm and readme_text:
        llm.register_tool(
            ToolSpec(
                name="check_placeholder",
                description="判断 README 是否为占位符",
                input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
                handler=lambda args: {"placeholder": llm.check_repo_placeholder(args.get("text", ""))},
            )
        )
        result = llm.run_tool_plan("判断 README 是否占位符", {"text": readme_text})
        calls = []
        if isinstance(result, dict):
            calls = result.get("calls") or result.get("results") or []
        elif isinstance(result, list):
            calls = result
        for r in calls:
            if isinstance(r, dict) and r.get("result", {}).get("placeholder"):
                status = "Placeholder"
                break

    return {
        "status": status,
        "has_readme": has_readme,
        "has_code": has_code,
        "last_commit": last_commit,
    }
