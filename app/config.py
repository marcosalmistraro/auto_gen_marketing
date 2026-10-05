import os
from dotenv import load_dotenv

# Load .env file if it exists (local dev)
# On Railway, environment variables are injected directly
load_dotenv()


class Settings:
    groq_api_key: str = os.getenv("GROQ_API_KEY", "")
    llm_model: str = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
    vision_model: str = os.getenv("VISION_MODEL", "qwen/qwen3.8-27b")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
    chroma_path: str = os.getenv("CHROMA_PATH", "./data/chroma")
    sqlite_path: str = os.getenv("SQLITE_PATH", "./data/images.db")
    max_chunk_tokens: int = int(os.getenv("MAX_CHUNK_TOKENS", "512"))
    chunk_overlap: int = int(os.getenv("CHUNK_OVERLAP", "50"))
    rag_threshold_tokens: int = int(os.getenv("RAG_THRESHOLD_TOKENS", "80000"))

    def __post_init__(self):
        if not self.groq_api_key:
            raise ValueError("GROQ_API_KEY is required")


settings = Settings()