"""出题接地 Agent（研究阶段）：LangChain 1.0 create_agent + 多个 Tavily 接地工具。

两阶段接地中的“阶段一”：Agent 自主选择 web_search_brief / web_search_full / web_extract
进行联网检索与网页抽取，最终产出一段“研究简报”纯文本；结构化题库在“阶段二”由稳定的
json_mode 链产出（见 quiz_chain.build_grounded_chain），因为 DeepSeek 对工具调用式结构化
输出（ToolStrategy）支持不稳定。

本模块提供：
- build_research_agent：组装研究 Agent（不强制结构化输出，稳定地以文本简报收尾）。
- extract_research_text：从消息里取研究简报文本（优先结尾 AI 文本，退化为拼接工具摘要）。
- extract_sources_from_messages：从工具 artifact 确定性抽取参考来源，杜绝模型编造 URL。
"""

from __future__ import annotations

from typing import Any, Optional

from langchain.agents import create_agent
from langchain.agents.middleware import ToolCallLimitMiddleware
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import BaseTool

from app.core.config import get_settings
from app.llm.search_tools import build_search_tools
from app.prompts.quiz_prompt import RESEARCH_PROMPT_V2

# 抽取来源工具名 -> 来源类型
_EXTRACT_TOOL_NAME = "web_extract"
_KB_TOOL_NAME = "search_knowledge_base"

_KIND_RANK = {"knowledge_base": 0, "extract": 1, "search": 2}


def build_research_agent(
    llm: Any,
    tools: Optional[list[BaseTool]] = None,
    system_prompt: str = RESEARCH_PROMPT_V2,
    tool_call_limit: Optional[int] = None,
) -> Any:
    """构建研究 Agent。tools 为 None 时用默认三联网工具；system_prompt 默认保持 V2。

    工具调用达到上限后会收到错误提示，迫使模型停止检索、用已有结果输出简报，
    避免大文档场景因持续检索耗尽 recursion_limit 而整单失败。
    """
    if tools is None:
        tools = build_search_tools()
    limit = (
        tool_call_limit
        if tool_call_limit is not None
        else get_settings().quiz_agent_tool_call_limit
    )
    middleware = []
    if limit > 0:
        middleware.append(
            ToolCallLimitMiddleware(run_limit=limit, exit_behavior="continue")
        )
    return create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_prompt,
        middleware=middleware,
    )


def extract_research_text(messages: Any, max_chars: int = 6000) -> str:
    """取研究简报文本：优先最后一条有正文的 AI 消息；否则拼接工具摘要兜底。"""
    if not messages:
        return ""
    for msg in reversed(list(messages)):
        if isinstance(msg, AIMessage) and isinstance(msg.content, str) and msg.content.strip():
            return msg.content.strip()[:max_chars]
    parts: list[str] = []
    for msg in messages:
        if isinstance(msg, ToolMessage) and isinstance(msg.content, str) and msg.content.strip():
            parts.append(msg.content.strip())
    return "\n".join(parts)[:max_chars]


def extract_sources_from_messages(
    messages: Any, max_sources: int = 8
) -> list[dict[str, Any]]:
    """从 Agent 消息列表抽取参考来源。

    仅信任工具 artifact 中的结果：知识库检索归为 kind="knowledge_base"，
    web_extract 归为 kind="extract"，其余搜索工具归为 kind="search"。
    联网按 URL 去重，知识库按 (doc_id, chunk_index) 去重；
    排序为知识库优先、其次网页抽取、最后联网搜索，组内按 score 降序。
    """
    if not messages:
        return []
    collected: list[dict[str, Any]] = []
    seen_web: set[str] = set()
    seen_kb: set[tuple[str, int]] = set()

    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        artifact = getattr(msg, "artifact", None)
        if not isinstance(artifact, dict):
            continue
        name = getattr(msg, "name", None)

        if name == _KB_TOOL_NAME:
            for item in artifact.get("results") or []:
                if not isinstance(item, dict):
                    continue
                doc_id = item.get("doc_id")
                if not doc_id:
                    continue
                try:
                    chunk_index = int(item.get("chunk_index") or 0)
                except (TypeError, ValueError):
                    chunk_index = 0
                key = (str(doc_id), chunk_index)
                if key in seen_kb:
                    continue
                seen_kb.add(key)
                page = item.get("page")
                collected.append(
                    {
                        "title": item.get("doc_name") or str(doc_id),
                        "url": "",
                        "score": item.get("score"),
                        "kind": "knowledge_base",
                        "doc_id": str(doc_id),
                        "chunk_index": chunk_index,
                        "page": page if isinstance(page, int) else None,
                        "snippet": item.get("snippet"),
                    }
                )
            continue

        kind = "extract" if name == _EXTRACT_TOOL_NAME else "search"
        for item in artifact.get("results") or []:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if not url or url in seen_web:
                continue
            seen_web.add(url)
            collected.append(
                {
                    "title": item.get("title") or url,
                    "url": url,
                    "score": item.get("score"),
                    "kind": kind,
                }
            )

    collected.sort(
        key=lambda s: (
            _KIND_RANK.get(s.get("kind"), 3),
            -(s.get("score") or 0.0),
        )
    )
    return collected[:max_sources]
