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
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import BaseTool

from app.llm.search_tools import build_search_tools
from app.prompts.quiz_prompt import RESEARCH_PROMPT_V2

# 抽取来源工具名 -> 来源类型
_EXTRACT_TOOL_NAME = "web_extract"


def build_research_agent(llm: Any, tools: Optional[list[BaseTool]] = None) -> Any:
    """构建研究 Agent。tools 为 None 时用默认三接地工具（web_search_brief/full、web_extract）。

    recursion_limit 等在 invoke 时通过 config 传入，不在此固化。
    """
    if tools is None:
        tools = build_search_tools()
    return create_agent(model=llm, tools=tools, system_prompt=RESEARCH_PROMPT_V2)


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
    messages: Any, max_sources: int = 6
) -> list[dict[str, Any]]:
    """从 Agent 消息列表抽取参考来源。

    仅信任工具 artifact 中的结果：web_extract 归为 kind="extract"，其余搜索工具归为 kind="search"。
    按 url 去重；排序时抽取来源优先、搜索来源按 score 降序；截断前 max_sources 条。
    """
    if not messages:
        return []
    collected: dict[str, dict[str, Any]] = {}
    for msg in messages:
        if not isinstance(msg, ToolMessage):
            continue
        artifact = getattr(msg, "artifact", None)
        if not isinstance(artifact, dict):
            continue
        kind = "extract" if getattr(msg, "name", None) == _EXTRACT_TOOL_NAME else "search"
        for item in artifact.get("results") or []:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if not url or url in collected:
                continue
            collected[url] = {
                "title": item.get("title") or url,
                "url": url,
                "score": item.get("score"),
                "kind": kind,
            }

    sources = list(collected.values())
    sources.sort(
        key=lambda s: (0 if s["kind"] == "extract" else 1, -(s["score"] or 0.0)),
    )
    return sources[:max_sources]
