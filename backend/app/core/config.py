from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 目录（app/core/config.py -> core -> app -> backend）
BASE_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    log_level: str = "INFO"

    # DeepSeek（OpenAI 兼容）
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"

    # 微信小程序（AppID 相对公开；AppSecret 为服务端密钥，仅后端持有，绝不下发到前端）
    wechat_appid: str = ""
    wechat_appsecret: str = ""

    # 出题链路参数（非 thinking 模式）
    quiz_temperature: float = 0.4
    quiz_max_tokens: int = 4096
    # 报告链路参数
    report_temperature: float = 0.5
    report_max_tokens: int = 2048

    llm_timeout: int = 30
    llm_max_retries: int = 2

    # 联网接地出题（Tavily 搜索 + 网页抽取）
    # 未配置 tavily_api_key 或 enable_web_search=False 时，出题自动降级为“未接地”链路
    tavily_api_key: str = ""
    enable_web_search: bool = True
    # 摘要检索实例：简单主题，仅返回摘要，结果条数偏多
    tavily_search_brief_max_results: int = 5
    # 全文检索实例：复杂主题，结果含正文，条数偏小以控 token
    tavily_search_full_max_results: int = 3
    tavily_search_full_depth: str = "advanced"
    # 网页抽取实例：用户给出 URL 时抓取整页正文
    tavily_extract_depth: str = "advanced"
    tavily_extract_format: str = "markdown"
    # 地区加权（Tavily country，仅 general topic 生效；空=全球）
    tavily_country: str = ""
    # Agent 工具循环上限，防止无限检索（每轮“模型→工具”约耗 2 步，16 足够多轮检索+抽取+结构化输出）
    quiz_agent_recursion_limit: int = 16
    # 单条检索/抽取正文注入模型前的截断长度，控制 token
    quiz_digest_max_chars: int = 2000
    # 异步出题任务：超时兜底秒数与进程内并发上限（单实例部署）
    quiz_job_timeout_seconds: int = 300
    quiz_job_max_concurrency: int = 2

    # MySQL
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "ai_learn"
    mysql_charset: str = "utf8mb4"
    mysql_pool_minsize: int = 1
    mysql_pool_maxsize: int = 10
    mysql_auto_init: bool = True

    # JWT
    jwt_secret: str = "dev-insecure-secret-change-me-in-production-0000"
    jwt_expire_days: int = 30


@lru_cache
def get_settings() -> Settings:
    return Settings()
