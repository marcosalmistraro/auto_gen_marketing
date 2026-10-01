from pydantic_settings import BaseSettings


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

    class Config:
        env_file = ".env"


settings = Settings()
