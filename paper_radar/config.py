import os
from dataclasses import dataclass
from typing import List, Optional

import yaml


@dataclass
class ConferenceConfig:
    name: str
    year: int
    arxiv_categories: List[str]
    keywords: List[str]
    source_priority: Optional[List[str]] = None
    openreview: Optional["OpenReviewConfig"] = None
    official_site: Optional["OfficialSiteConfig"] = None


@dataclass
class OpenReviewConfig:
    venue_id: Optional[str] = None
    limit: Optional[int] = 200


@dataclass
class OfficialSiteConfig:
    list_url: Optional[str] = None
    item_selector: Optional[str] = None
    title_selector: Optional[str] = None
    authors_selector: Optional[str] = None
    affiliations_selector: Optional[str] = None
    abstract_selector: Optional[str] = None
    pdf_selector: Optional[str] = None
    supplemental_selector: Optional[str] = None


@dataclass
class MonitoringConfig:
    deadline_lag_days: int
    ccf_repo_dir: str
    arxiv_max_results: int
    arxiv_batch_days: int


@dataclass
class LLMConfig:
    provider: str
    model: str
    max_batch_size: int


@dataclass
class StorageConfig:
    db_path: str
    site_dir: str


@dataclass
class SecretConfig:
    llm_api_key_env: str
    github_token_env: str


@dataclass
class SiteConfig:
    author: str
    title: str


@dataclass
class AppConfig:
    conferences: List[ConferenceConfig]
    monitoring: MonitoringConfig
    llm: LLMConfig
    storage: StorageConfig
    secrets: SecretConfig
    site: SiteConfig


def load_config(path: str = "config.yml") -> AppConfig:
    if not os.path.exists(path):
        raise FileNotFoundError(f"找不到配置文件 {path}，请先复制 config.yml.example")
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    conferences = []
    for c in data.get("conferences", []):
        openreview_cfg = c.get("openreview")
        official_cfg = c.get("official_site")
        c["openreview"] = OpenReviewConfig(**openreview_cfg) if openreview_cfg else None
        c["official_site"] = OfficialSiteConfig(**official_cfg) if official_cfg else None
        conferences.append(ConferenceConfig(**c))
    monitoring = MonitoringConfig(**data["monitoring"])
    llm = LLMConfig(**data["llm"])
    storage = StorageConfig(**data["storage"])
    secrets = SecretConfig(**data["secrets"])
    site = SiteConfig(**data["site"])
    return AppConfig(
        conferences=conferences,
        monitoring=monitoring,
        llm=llm,
        storage=storage,
        secrets=secrets,
        site=site,
    )


def get_env_or_raise(key: str) -> str:
    value: Optional[str] = os.environ.get(key)
    if not value:
        raise EnvironmentError(f"缺少必要环境变量：{key}")
    return value
