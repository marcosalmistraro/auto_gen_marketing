import chromadb
from chromadb.config import Settings as ChromaSettings
from fastembed import TextEmbedding
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


def _get_embedder() -> TextEmbedding:
    global _embedding_model
    if _embedding_model is None:
        _embedding_model = TextEmbedding(model_name=settings.embedding_model)
    return _embedding_model


def _embed(texts: list[str]) -> list[list[float]]:
    embedder = _get_embedder()
    return [emb.tolist() for emb in embedder.embed(texts)]


def _collection_name(company_id: str) -> str:
    # One collection per company - clean separation, no cross-company bleed
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
    collection = client.get_or_create_collection(name=_collection_name(company_id))

    embeddings = _embed(chunks)

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

    try:
        collection = client.get_collection(name=_collection_name(company_id))
    except Exception:
        return []

    query_embedding = _embed([query])

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


def delete_company(company_id: str) -> bool:
    client = _get_client()
    try:
        client.delete_collection(name=_collection_name(company_id))
        return True
    except Exception:
        return False


def list_companies() -> list[dict]:
    client = _get_client()
    try:
        collections = client.list_collections()
    except Exception:
        return []

    result = []
    for col in collections:
        name = col if isinstance(col, str) else col.name
        if not name.startswith("company_"):
            continue
        try:
            collection = client.get_collection(name)
            all_data = collection.get(include=["metadatas"])
            metadatas = all_data["metadatas"] or []
        except Exception:
            continue

        company_id = metadatas[0]["company_id"] if metadatas else name[len("company_"):].replace("_", "-")
        role = metadatas[0]["role"] if metadatas else "unknown"
        chunk_types: dict[str, int] = {}
        for m in metadatas:
            ct = m.get("chunk_type", "text")
            chunk_types[ct] = chunk_types.get(ct, 0) + 1

        result.append({
            "company_id": company_id,
            "role": role,
            "total_chunks": len(metadatas),
            "text_chunks": chunk_types.get("text", 0),
            "table_chunks": chunk_types.get("table", 0),
            "image_descriptions": chunk_types.get("image_description", 0),
        })

    return result
