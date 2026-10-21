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
    # Agent 单次运行最多执行的工具调用次数；达到后拦截多余调用，让模型用已有结果收尾
    quiz_agent_tool_call_limit: int = 10
    # Agent 图执行步数上限，需高于“工具调用上限 + 模型收尾”所需步数
    quiz_agent_recursion_limit: int = 30
    # 单条检索/抽取正文注入模型前的截断长度，控制 token
    quiz_digest_max_chars: int = 2000
    # 异步出题任务：超时兜底秒数与进程内并发上限（单实例部署）
    quiz_job_timeout_seconds: int = 300
    quiz_job_max_concurrency: int = 2

    # 个人知识库（百炼 Embedding + 本地 Chroma）
    enable_knowledge_base: bool = True
    dashscope_api_key: str = ""
    embedding_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    embedding_model: str = "text-embedding-v4"
    embedding_dimensions: int = 1024
    embedding_batch_size: int = 8
    embedding_timeout: int = 30
    embedding_max_retries: int = 2
    chroma_persist_dir: str = "data/chroma"
    kb_upload_dir: str = "data/knowledge_base"
    kb_max_file_mb: int = 10
    kb_chunk_size: int = 800
    kb_chunk_overlap: int = 100
    kb_max_chunks_per_doc: int = 2000
    kb_retrieval_top_k: int = 4
    # 首页出题知识库检索最低相关度（0-1）；低于该值的分块不进入研究简报
    kb_min_relevance_score: float = 0.60
    kb_ingestion_concurrency: int = 2

    # 题目配图（百炼 qwen-image-3.0 同步生图 + 腾讯云 COS 公有读桶）
    enable_image_generation: bool = True
    image_base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    image_model: str = "qwen-image-3.0"
    image_size: str = "512*512"
    image_timeout_seconds: int = 45
    image_max_concurrency: int = 6
    image_daily_limit: int = 100
    image_max_retries: int = 3
    image_retry_backoff_seconds: float = 2.0
    cos_secret_id: str = ""
    cos_secret_key: str = ""
    cos_region: str = ""
    cos_bucket: str = ""
    cos_public_base_url: str = ""
    cos_key_prefix: str = "question-images"
    # 用户头像：COS 公有读对象前缀与上传大小上限
    cos_avatar_prefix: str = "avatars"
    avatar_max_file_mb: int = 2

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
    # 连接会话时区；现有历史数据不回填，仅保证新写入时间为北京时间
    mysql_time_zone: str = "+08:00"

    # JWT
    jwt_secret: str = "dev-insecure-secret-change-me-in-production-0000"
    jwt_expire_days: int = 30

    @property
    def chroma_persist_path(self) -> Path:
        return _resolve_backend_path(self.chroma_persist_dir)

    @property
    def kb_upload_path(self) -> Path:
        return _resolve_backend_path(self.kb_upload_dir)

    @property
    def kb_max_file_bytes(self) -> int:
        return self.kb_max_file_mb * 1024 * 1024

    @property
    def knowledge_base_ready(self) -> bool:
        return bool(self.enable_knowledge_base and self.dashscope_api_key)

    @property
    def avatar_max_file_bytes(self) -> int:
        return self.avatar_max_file_mb * 1024 * 1024

    @property
    def cos_ready(self) -> bool:
        return bool(
            self.cos_secret_id
            and self.cos_secret_key
            and self.cos_region
            and self.cos_bucket
        )

    @property
    def image_generation_ready(self) -> bool:
        return bool(
            self.enable_image_generation
            and self.dashscope_api_key
            and self.cos_ready
        )


def _resolve_backend_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else BASE_DIR / path


@lru_cache
def get_settings() -> Settings:
    return Settings()
