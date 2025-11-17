"""LLM 通信模块，优先 deepseek，提供批处理摘要、聚类与趋势总结能力，
并实现最小 MCP 工具调用协议（注册本地工具、解析调用、返回结构化结果）。"""

import json
import logging
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from openai import OpenAI

logger = logging.getLogger(__name__)


@dataclass
class ToolSpec:
    name: str
    description: str
    input_schema: Dict
    handler: Callable[[Dict], Dict]


class LLMClient:
    def __init__(self, provider: str, model: str, api_key: str):
        base_url = "https://api.deepseek.com" if provider == "deepseek" else None
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.tools: Dict[str, ToolSpec] = {}

    def register_tool(self, spec: ToolSpec):
        self.tools[spec.name] = spec

    def _chat(self, messages: List[Dict], response_format: Optional[Dict] = None) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            response_format=response_format or {"type": "text"},
        )
        return resp.choices[0].message.content

    def _chat_json(self, messages: List[Dict], force_object: bool = True) -> Optional[Dict]:
        for _ in range(2):
            try:
                response_format = {"type": "json_object"} if force_object else None
                content = self._chat(messages, response_format=response_format)
                return json.loads(content)
            except Exception as exc:
                logger.warning("JSON 解析失败，重试一次: %s", exc)
        return None

    def batch_summarize(self, papers: List[Tuple[int, str, str]]) -> List[Tuple[int, str, str]]:
        if not papers:
            return []
        payload = [
            {"id": pid, "title": title, "abstract": abstract}
            for pid, title, abstract in papers
        ]
        system = "你是资深论文助手，请逐条阅读 JSON 中的论文摘要，生成英文与中文一句话核心贡献。"
        user = (
            "请输出与输入数组等长的 JSON 数组，每个元素包含 id, tldr_en, tldr_zh，"
            "不得遗漏任何论文，不得添加额外文本。输入数据：" + json.dumps(payload, ensure_ascii=False)
        )
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        data = self._chat_json(messages, force_object=False)
        if not data:
            return []
        results = []
        for item in data:
            try:
                results.append((int(item["id"]), item.get("tldr_en", ""), item.get("tldr_zh", "")))
            except Exception:
                continue
        return results

    def cluster_papers(self, papers: List[Dict]) -> List[Tuple[int, str]]:
        if not papers:
            return []
        payload = [{"id": p["id"], "title": p["title"], "abstract": p.get("abstract", "")[:800]} for p in papers]
        system = (
            "你是 AI 领域科学家，请阅读全部摘要，将论文自动聚类为 5-8 个主题。"
            "以 JSON 数组返回，每个元素包含 id 和 label（主题名称）。"
        )
        user = "输入数据：" + json.dumps(payload, ensure_ascii=False)
        data = self._chat_json(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            force_object=False,
        )
        if not data:
            return []
        return [(int(item.get("id")), item.get("label", "未知主题")) for item in data if item.get("id") is not None]

    def summarize_trend(self, clusters: List[Tuple[str, int]]) -> Optional[str]:
        if not clusters:
            return None
        payload = [{"label": label, "count": count} for label, count in clusters]
        system = "请根据主题词频，用中文写一段 200 字左右的技术趋势总结。"
        user = "主题数据：" + json.dumps(payload, ensure_ascii=False)
        try:
            return self._chat([{"role": "system", "content": system}, {"role": "user", "content": user}])
        except Exception as exc:
            logger.error("趋势总结失败: %s", exc)
            return None

    def check_repo_placeholder(self, readme_text: str) -> bool:
        prompt = (
            "判断 README 是否属于占位符（如 code coming soon、WIP、empty）。"
            "只回答 true 或 false。内容：" + readme_text[:4000]
        )
        try:
            result = self._chat(
                [{"role": "system", "content": "你是严格的代码审核员，只输出 true 或 false"}, {"role": "user", "content": prompt}]
            )
            return "true" in result.lower()
        except Exception:
            return False

    def run_tool_plan(self, task: str, payload: Dict) -> Dict:
        """最小 MCP 循环：LLM 给出工具调用计划(JSON list)，本地执行后再让 LLM 汇总。"""

        if not self.tools:
            return {}

        plan_prompt = [
            {
                "role": "system",
                "content": "你是任务规划器，返回 JSON 数组列出要调用的工具及输入，不要添加描述",
            },
            {
                "role": "user",
                "content": f"任务: {task}\n可用工具: {list(self.tools.keys())}\n上下文: {json.dumps(payload, ensure_ascii=False)}",
            },
        ]
        calls = self._chat_json(plan_prompt, force_object=False) or []
        executed = []
        for call in calls:
            name = call.get("tool")
            spec = self.tools.get(name)
            if not spec:
                continue
            try:
                result = spec.handler(call.get("input", {}))
                executed.append({"tool": name, "result": result})
            except Exception as exc:
                executed.append({"tool": name, "error": str(exc)})

        summarize_prompt = [
            {
                "role": "system",
                "content": "你是工具结果汇总助手，请基于结果生成结构化 JSON，不要输出多余文本",
            },
            {
                "role": "user",
                "content": json.dumps({"task": task, "calls": executed}, ensure_ascii=False),
            },
        ]
        return self._chat_json(summarize_prompt) or {}
