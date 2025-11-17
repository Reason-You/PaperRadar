"""PDF 相关工具：提取文本和 GitHub 链接，优先少页快速解析。"""

import io
import logging
import re
from typing import List

import requests
from pypdf import PdfReader

logger = logging.getLogger(__name__)


GITHUB_PATTERN = re.compile(r"https?://github\.com/[\w\-\.]+/[\w\-\.]+", re.IGNORECASE)


def extract_github_from_pdf(pdf_url: str, max_pages: int = 3) -> List[str]:
    """下载 PDF 并提取前 max_pages 页的 GitHub 链接。"""

    if not pdf_url:
        return []
    try:
        resp = requests.get(pdf_url, timeout=20)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("下载 PDF 失败 %s: %s", pdf_url, exc)
        return []

    try:
        reader = PdfReader(io.BytesIO(resp.content))
        text_parts = []
        for page in reader.pages[:max_pages]:
            try:
                text_parts.append(page.extract_text() or "")
            except Exception:
                continue
        text = "\n".join(text_parts)
        return list({m.group(0) for m in GITHUB_PATTERN.finditer(text)})
    except Exception as exc:
        logger.warning("解析 PDF 失败 %s: %s", pdf_url, exc)
        return []
