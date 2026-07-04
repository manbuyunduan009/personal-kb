from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    docs_root: Path = Path(r"D:\vscode\动效\docs")
    app_data_dir: Path = Path("./data")
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
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
    def chroma_path(self) -> Path:
        return self.app_data_dir / "chroma"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.app_data_dir.mkdir(parents=True, exist_ok=True)
    return settings
