import logging
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from paper_radar import db
from paper_radar.arxiv_client import extract_github_links
from paper_radar.ccf_monitor import load_deadlines, select_triggered_conferences, sync_ccf_repo
from paper_radar.code_verifier import verify_repo
from paper_radar.config import AppConfig, get_env_or_raise
from paper_radar.collector import collect_papers
from paper_radar.llm_mcp import LLMClient
from paper_radar.pdf_utils import extract_github_from_pdf
from paper_radar.site_generator import generate_site

logger = logging.getLogger(__name__)


class Pipeline:
    def __init__(self, config: AppConfig):
        load_dotenv()
        self.config = config
        self.db_path = config.storage.db_path
        self.site_dir = config.storage.site_dir
        self._llm_client: Optional[LLMClient] = None
        try:
            api_key = get_env_or_raise(config.secrets.llm_api_key_env)
            self._llm_client = LLMClient(config.llm.provider, config.llm.model, api_key)
        except Exception:
            logger.warning("未找到 LLM API Key，跳过摘要/聚类/趋势生成")
            self._llm_client = None
        self.github_token = None
        try:
            self.github_token = get_env_or_raise(config.secrets.github_token_env)
        except Exception:
            logger.warning("未设置 GitHub Token，将匿名调用 GitHub API")

    def run(self):
        logger.info("启动 PaperRadar 工作流")
        Path(self.config.monitoring.ccf_repo_dir).parent.mkdir(parents=True, exist_ok=True)
        sync_ccf_repo(self.config.monitoring.ccf_repo_dir)
        deadlines = load_deadlines(self.config.monitoring.ccf_repo_dir)
        triggered = select_triggered_conferences(
            self.db_path,
            self.config.conferences,
            deadlines,
            self.config.monitoring.deadline_lag_days,
        )
        for conf in triggered:
            self.process_conference(conf.name, conf.year, conf.arxiv_categories, conf.keywords)
        self.render_site()

    def process_conference(self, name: str, year: int, categories, keywords):
        logger.info("处理会议 %s %s", name, year)
        # 1. 多源抓取
        conf_cfg = next(c for c in self.config.conferences if c.name == name and c.year == year)
        papers = collect_papers(conf_cfg, self.config.monitoring, categories, keywords)
        db.insert_papers(self.db_path, papers)
        # 2. 摘要批处理
        if self._llm_client:
            batch = db.fetch_papers_without_summary(
                self.db_path, name, year, self.config.llm.max_batch_size
            )
            while batch:
                summaries = self._llm_client.batch_summarize(batch)
                db.save_summaries(self.db_path, summaries)
                batch = db.fetch_papers_without_summary(
                    self.db_path, name, year, self.config.llm.max_batch_size
                )
        # 3. 聚类与趋势
        if self._llm_client:
            all_papers = db.fetch_papers(self.db_path, name, year)
            clusters = self._llm_client.cluster_papers(all_papers)
            db.save_clusters(self.db_path, name, year, clusters)
            cluster_counts = db.fetch_cluster_counts(self.db_path, name, year)
            trend = self._llm_client.summarize_trend(cluster_counts)
            if trend:
                db.save_trend(self.db_path, name, year, trend)
        # 4. 代码验证
        all_papers = db.fetch_papers(self.db_path, name, year)
        for paper in all_papers:
            links = set(extract_github_links(paper.get("abstract", "")))
            pdf_links = extract_github_from_pdf(paper.get("pdf_url"))
            links.update(pdf_links)
            for link in links:
                result = verify_repo(link, self.github_token, self._llm_client, paper.get("created_at"))
                db.save_code_link(
                    self.db_path,
                    paper["id"],
                    link,
                    result["status"],
                    result["last_commit"],
                    result["has_readme"],
                    result["has_code"],
                )

    def render_site(self):
        generate_site(
            self.db_path,
            self.site_dir,
            str(Path(__file__).parent / "templates"),
            {"author": self.config.site.author, "title": self.config.site.title},
        )
        logger.info("静态站点生成完成 -> %s", self.site_dir)
