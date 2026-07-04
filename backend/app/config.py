import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv


class Settings(BaseSettings):
    docs_root: Path = Path(r"D:\vscode\动效\docs")
    app_data_dir: Path = Path("./data")
    embedding_provider: str = "hash"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    hf_endpoint: str = "https://hf-mirror.com"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def sqlite_path(self) -> Path:
        return self.app_data_dir / "personal_kb.sqlite3"

    @property
    def vector_sqlite_path(self) -> Path:
        return self.app_data_dir / "vectors.sqlite3"


@lru_cache
def get_settings() -> Settings:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(env_path, override=True)
    settings = Settings()
    if settings.hf_endpoint:
        os.environ.setdefault("HF_ENDPOINT", settings.hf_endpoint)
    settings.app_data_dir.mkdir(parents=True, exist_ok=True)
    return settings
