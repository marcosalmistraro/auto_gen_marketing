from app.config import settings


def chunk_text(text: str, chunk_size: int = None, overlap: int = None) -> list[str]:
    """
    Split text into overlapping chunks by word count.
    """
    chunk_size = chunk_size or settings.max_chunk_tokens
    overlap = overlap or settings.chunk_overlap

    words = text.split()
    if not words:
        return []

    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        chunks.append(chunk)
        start += chunk_size - overlap

    return chunks


def estimate_tokens(text: str) -> int:
    """
    Rough token estimate: 1 token ≈ 0.75 words.
    Used to decide full-context vs RAG — not for billing.
    """
    return int(len(text.split()) / 0.75)
