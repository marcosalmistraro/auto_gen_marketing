from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict


class Settings(BaseSettings):
    groq_api_key: str
    llm_model: str = "llama-3.3-70b-versatile"
    vision_model: str = "llama-3.2-11b-vision-preview"
    embedding_model: str = "all-MiniLM-L6-v2"
    chroma_path: str = "./data/chroma"
    sqlite_path: str = "./data/images.db"
    max_chunk_tokens: int = 512
    chunk_overlap: int = 50
    rag_threshold_tokens: int = 80000

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # ignore extra env vars from Railway
    )


settings = Settings()