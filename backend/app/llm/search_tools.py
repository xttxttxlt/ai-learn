"""联网接地工具：薄封装官方 langchain-tavily 的 TavilySearch / TavilyExtract。

多实例工具策略（交给 Agent 自主选择）：
- web_search_brief：摘要检索（include_raw_content=False），简单主题快速取摘要，条数偏多。
- web_search_full：全文检索（include_raw_content=True, advanced），复杂主题取正文，条数偏小控 token。
- web_extract：网页抽取，用户给出 URL（或搜索定位到权威 URL）时抓整页正文。

用 StructuredTool(response_format="content_and_artifact") 封装官方工具：
- content：给模型看的精炼摘要（每条正文按 QUIZ_DIGEST_MAX_CHARS 截断，控 token）；
- artifact：精简来源结构（title/url/score），供确定性抽取 sources，杜绝模型编造 URL。

底层官方工具的 invoke 直接返回 dict；异常/无结果时返回可读提示 + 空来源，交由 Agent 决定是否换参重试或降级。
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from langchain_core.tools import BaseTool, StructuredTool
from langchain_tavily import TavilyExtract, TavilySearch

from app.core.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger("search_tools")

SearchDepth = Literal["basic", "advanced", "fast", "ultra-fast"]
TimeRange = Literal["day", "week", "month", "year"]

BRIEF_DESCRIPTION = (
    "摘要检索：按关键词联网搜索，返回多条结果的标题、链接与摘要（不含全文）。"
    "适合简单概念、常识性事实、快速确认。可按需设置 search_depth、time_range、"
    "include_domains、exclude_domains 收敛范围。"
)
FULL_DESCRIPTION = (
    "全文检索：按关键词联网搜索并返回结果正文（信息更全、条数更少）。"
    "适合复杂、冷门或摘要不足以准确出题的主题。可设置 time_range、include_domains、exclude_domains。"
)
EXTRACT_DESCRIPTION = (
    "网页抽取：给定一个或多个 URL，抓取其整页正文（markdown）。"
    "当用户输入包含网页链接，或需要用搜索定位到的权威 URL 取全文时使用。"
)


def _truncate(text: Any, limit: int) -> str:
    text = text or ""
    if not isinstance(text, str):
        text = str(text)
    return text if len(text) <= limit else text[:limit].rstrip() + "…"


def _search_digest(raw: Any, limit: int) -> str:
    if isinstance(raw, str):  # handle_tool_error 返回的错误信息字符串
        return f"[搜索未成功] {raw}"
    if not isinstance(raw, dict):
        return "[无搜索结果]"
    if raw.get("error"):
        return f"[搜索出错] {raw['error']}"
    parts: list[str] = []
    if raw.get("answer"):
        parts.append(f"摘要答案：{raw['answer']}")
    for r in raw.get("results") or []:
        title = r.get("title") or ""
        url = r.get("url") or ""
        body = r.get("raw_content") or r.get("content") or ""
        parts.append(f"- {title}\n  URL: {url}\n  正文: {_truncate(body, limit)}")
    return "\n".join(parts) if parts else "[无搜索结果]"


def _search_artifact(raw: Any) -> dict:
    if not isinstance(raw, dict):
        return {"results": []}
    out = []
    for r in raw.get("results") or []:
        url = r.get("url")
        if not url:
            continue
        out.append({"title": r.get("title") or url, "url": url, "score": r.get("score")})
    return {"results": out, "answer": raw.get("answer")}


def _extract_digest(raw: Any, limit: int) -> str:
    if isinstance(raw, str):
        return f"[抽取未成功] {raw}"
    if not isinstance(raw, dict):
        return "[无抽取结果]"
    if raw.get("error"):
        return f"[抽取出错] {raw['error']}"
    parts: list[str] = []
    for r in raw.get("results") or []:
        url = r.get("url") or ""
        body = r.get("raw_content") or ""
        parts.append(f"- URL: {url}\n  正文: {_truncate(body, limit)}")
    failed = raw.get("failed_results") or []
    if failed:
        parts.append(f"[抽取失败的URL] {failed}")
    return "\n".join(parts) if parts else "[无抽取结果]"


def _extract_artifact(raw: Any) -> dict:
    if not isinstance(raw, dict):
        return {"results": [], "failed_results": []}
    out = []
    for r in raw.get("results") or []:
        url = r.get("url")
        if not url:
            continue
        out.append({"title": r.get("title") or url, "url": url})
    return {"results": out, "failed_results": raw.get("failed_results") or []}


def make_search_tool(name: str, description: str, base: Any, digest_limit: int) -> BaseTool:
    """把一个 TavilySearch 实例封装成具名 content_and_artifact 工具。base 可注入（测试用）。"""

    def _run(
        query: str,
        search_depth: Optional[SearchDepth] = None,
        time_range: Optional[TimeRange] = None,
        include_domains: Optional[list[str]] = None,
        exclude_domains: Optional[list[str]] = None,
    ) -> tuple[str, dict]:
        args: dict[str, Any] = {"query": query}
        if search_depth:
            args["search_depth"] = search_depth
        if time_range:
            args["time_range"] = time_range
        if include_domains:
            args["include_domains"] = include_domains
        if exclude_domains:
            args["exclude_domains"] = exclude_domains
        try:
            raw = base.invoke(args)
        except Exception as exc:  # noqa: BLE001
            logger.warning("tavily_search_failed", tool=name, error=str(exc))
            return f"[搜索失败] {exc}", {"results": []}
        return _search_digest(raw, digest_limit), _search_artifact(raw)

    return StructuredTool.from_function(
        func=_run, name=name, description=description, response_format="content_and_artifact"
    )


def make_extract_tool(name: str, description: str, base: Any, digest_limit: int) -> BaseTool:
    """把一个 TavilyExtract 实例封装成具名 content_and_artifact 工具。base 可注入（测试用）。"""

    def _run(
        urls: list[str],
        extract_depth: Optional[Literal["basic", "advanced"]] = None,
        query: Optional[str] = None,
    ) -> tuple[str, dict]:
        args: dict[str, Any] = {"urls": urls}
        if extract_depth:
            args["extract_depth"] = extract_depth
        if query:
            args["query"] = query
        try:
            raw = base.invoke(args)
        except Exception as exc:  # noqa: BLE001
            logger.warning("tavily_extract_failed", error=str(exc))
            return f"[抽取失败] {exc}", {"results": [], "failed_results": list(urls)}
        return _extract_digest(raw, digest_limit), _extract_artifact(raw)

    return StructuredTool.from_function(
        func=_run, name=name, description=description, response_format="content_and_artifact"
    )


def build_search_tools(settings: Optional[Settings] = None) -> list[BaseTool]:
    """构建三个具名接地工具：web_search_brief / web_search_full / web_extract。"""
    s = settings or get_settings()
    key = s.tavily_api_key
    country = s.tavily_country or None
    limit = s.quiz_digest_max_chars

    brief_base = TavilySearch(
        tavily_api_key=key,
        max_results=s.tavily_search_brief_max_results,
        include_answer=True,
        include_raw_content=False,
        topic="general",
        country=country,
    )
    full_base = TavilySearch(
        tavily_api_key=key,
        max_results=s.tavily_search_full_max_results,
        include_answer=True,
        include_raw_content=True,
        search_depth=s.tavily_search_full_depth,
        topic="general",
        country=country,
    )
    extract_base = TavilyExtract(
        tavily_api_key=key,
        extract_depth=s.tavily_extract_depth,
        format=s.tavily_extract_format,
    )

    return [
        make_search_tool("web_search_brief", BRIEF_DESCRIPTION, brief_base, limit),
        make_search_tool("web_search_full", FULL_DESCRIPTION, full_base, limit),
        make_extract_tool("web_extract", EXTRACT_DESCRIPTION, extract_base, limit),
    ]
