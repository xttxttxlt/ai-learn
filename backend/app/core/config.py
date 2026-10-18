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

    # 出题链路参数（非 thinking 模式）
    quiz_temperature: float = 0.4
    quiz_max_tokens: int = 4096
    # 报告链路参数
    report_temperature: float = 0.5
    report_max_tokens: int = 2048

    llm_timeout: int = 30
    llm_max_retries: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()
