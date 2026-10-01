import chromadb
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer
from app.config import settings

_chroma_client = None
_embedding_model = None


def _get_client() -> chromadb.Client:
    global _chroma_client
    if _chroma_client is None:
        _chroma_client = chromadb.PersistentClient(
            path=settings.chroma_path,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
    return _chroma_client


def _get_embedder() -> SentenceTransformer:
    global _embedding_model
    if _embedding_model is None:
        # 22M params, runs on CPU, ~10ms per chunk
        # Good enough for standard English business text
        _embedding_model = SentenceTransformer(settings.embedding_model)
    return _embedding_model


def _collection_name(company_id: str) -> str:
    # One collection per company — clean separation, no cross-company bleed
    return f"company_{company_id.replace('-', '_')}"


def store_chunks(
    company_id: str,
    role: str,
    chunks: list[str],
    chunk_type: str = "text",  # "text" | "table" | "image_description"
) -> int:
    if not chunks:
        return 0

    client = _get_client()
    embedder = _get_embedder()
    collection = client.get_or_create_collection(name=_collection_name(company_id))

    embeddings = embedder.encode(chunks, show_progress_bar=False).tolist()

    existing = collection.count()
    ids = [f"{chunk_type}_{existing + i}" for i in range(len(chunks))]
    metadatas = [
        {
            "company_id": company_id,
            "role": role,
            "chunk_type": chunk_type,
            "chunk_index": existing + i,
        }
        for i in range(len(chunks))
    ]

    collection.add(
        ids=ids,
        embeddings=embeddings,
        documents=chunks,
        metadatas=metadatas,
    )
    return len(chunks)


def retrieve_chunks(
    company_id: str,
    query: str,
    n_results: int = 5,
    chunk_type: str = None,
) -> list[str]:
    client = _get_client()
    embedder = _get_embedder()

    try:
        collection = client.get_collection(name=_collection_name(company_id))
    except Exception:
        return []

    query_embedding = embedder.encode([query], show_progress_bar=False).tolist()

    where = {"company_id": company_id}
    if chunk_type:
        where["chunk_type"] = chunk_type

    results = collection.query(
        query_embeddings=query_embedding,
        n_results=min(n_results, collection.count()),
        where=where,
    )
    return results["documents"][0] if results["documents"] else []


def get_all_chunks(company_id: str) -> list[str]:
    client = _get_client()
    try:
        collection = client.get_collection(name=_collection_name(company_id))
    except Exception:
        return []

    all_docs = collection.get()
    return all_docs["documents"] or []
