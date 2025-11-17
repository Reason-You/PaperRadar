# PaperRadar（论文雷达）

PaperRadar 是一个零服务器、全自动的工作流，监控顶级 AI/ML/CV/NLP 会议，抓取论文元数据，使用优先 deepseek 的 LLM 完成批量摘要、聚类、趋势分析，并生成可部署到 GitHub Pages 的静态网站。

## 核心特性
- **零后端**：仅依赖 GitHub Actions + SQLite + 静态文件。
- **低成本 LLM**：批处理摘要/聚类/趋势分析，优先 deepseek，兼容 OpenAI。
- **自动化采集**：定期同步 ccf-deadlines，截止后自动触发 arXiv 监控与数据入库。
- **开源代码核验**：利用 GitHub API + LLM 过滤“code coming soon”等占位仓库。
- **静态站点**：前端提供搜索、主题筛选、代码状态过滤，内置词云和柱状图可视化。

## 快速开始
1. 安装依赖
   ```bash
   pip install -r requirements.txt
   ```
2. 复制配置并按需修改
   ```bash
   cp config.yml.example config.yml
   # 根据需要调整会议、arXiv 类别、批处理大小等
   ```
3. 配置环境变量（本地使用 .env，生产使用 GitHub Secrets）
   ```bash
   export DEEPSEEK_API_KEY=xxx   # 或 OPENAI_API_KEY
   export GITHUB_TOKEN=xxx       # 用于 GitHub 仓库验证
   ```
4. 初始化数据库
   ```bash
   python setup_db.py
   ```
5. 运行完整流水线（本地测试）
   ```bash
   python run_pipeline.py
   ```

## 模块说明
- `paper_radar/config.py`：加载配置，校验环境变量。
- `paper_radar/ccf_monitor.py`：同步 `ccf-deadlines`，基于截稿 + 滞后天数判定触发会议。
- `paper_radar/arxiv_client.py`：按会议关键词/类别调用 arXiv API，抽取 GitHub 链接，解析作者机构与补充链接（若有）。
- `paper_radar/collector.py`：多源采集（OpenReview → 官网爬取 → arXiv），补齐作者、机构、摘要、PDF/补充材料等元数据并按优先级去重入库。
- `paper_radar/llm_mcp.py`：LLM 通信层，批处理 TL;DR、聚类与趋势总结，优先 deepseek。
- `paper_radar/code_verifier.py`：GitHub API + LLM 工具链核验，校验 README、代码文件、提交日期，过滤占位仓库。
- `paper_radar/pdf_utils.py`：PDF 解析并优先提取 GitHub 链接。
- `paper_radar/site_generator.py`：Jinja2 渲染静态站点，提供搜索、主题/代码过滤、词云与柱状图。
- `paper_radar/workflow.py`：端到端编排，串联监控、抓取、分析、站点生成。

## GitHub Actions
`.github/workflows/run.yml` 配置了每日定时任务，会：
1. 安装依赖
2. 运行 `setup_db.py` 初始化/迁移数据库
3. 执行 `run_pipeline.py`
4. 将更新的 `paper_radar.db` 与 `_site` 静态文件自动 commit & push（确保在仓库启用 GitHub Pages 指向 `_site`）。

## 配置要点
- 默认优先使用 `DEEPSEEK_API_KEY`。如需 OpenAI，将 `llm.provider` 设为 `openai` 并提供 `OPENAI_API_KEY`。
- GitHub API 调用建议配置 `GITHUB_TOKEN`，否则退回匿名配额。
- `monitoring.deadline_lag_days` 控制截稿后多久触发采集；`arxiv_batch_days` 控制每日监控窗口。
- `conferences[].source_priority` 决定抓取顺序，支持 `openreview`、`official`、`arxiv`。
- 官网采集可配置 `authors_selector`、`affiliations_selector`、`abstract_selector`、`pdf_selector`、`supplemental_selector` 指定 CSS 选择器；未提供时默认读取元素 `data-*` 属性。

## 目录结构
- `paper_radar/`：核心 Python 模块与 Jinja2 模板
- `_site/`：生成的静态页面（自动生成）
- `paper_radar.db`：SQLite 数据库（自动生成并存库）

## 注意事项
- **不要提交任何密钥**：`.env` 已在 `.gitignore` 中。
- 若无 LLM/Token，流水线会跳过摘要、聚类、趋势和占位检测，仍可完成抓取与站点生成。
- 词云与可视化由前端 JS 完成，部署到 GitHub Pages 即可生效。
- 官网爬虫需按会议自定义选择器；OpenReview 需提供 `venue_id`。
