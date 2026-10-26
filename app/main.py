from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from contextlib import asynccontextmanager

from app.config import settings
from app.models.schemas import (
    CompanyRole, UploadResponse, GenerateRequest, GenerateResponse
)
from app.services.pdf_extractor import extract_pdf
from app.services.vector_store import store_chunks, retrieve_chunks, get_all_chunks, list_companies, delete_company
from app.services.image_store import init_db, store_image, get_images_for_company, get_image_counts, delete_company_images, get_image_with_ext
from app.services.generator import describe_image, generate_article
from app.utils.chunker import chunk_text, estimate_tokens


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="ML6 Marketing Collateral API",
    description="Automated B2B marketing article generation from company PDFs",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Endpoint 1: Upload ────────────────────────────────────────────────────────

@app.post("/upload", response_model=UploadResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    company_id: str = Form(...),
    role: CompanyRole = Form(...),
):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    file_bytes = await file.read()

    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    # 1. Extract text, tables, images from PDF
    extracted = extract_pdf(file_bytes)

    # 2. Chunk and embed text
    text_chunks = []
    for block in extracted.text_blocks:
        text_chunks.extend(chunk_text(block))

    table_chunks = []
    for table_md in extracted.table_blocks:
        table_chunks.extend(chunk_text(table_md))

    chunks_stored = 0
    chunks_stored += store_chunks(company_id, role.value, text_chunks, chunk_type="text")
    chunks_stored += store_chunks(company_id, role.value, table_chunks, chunk_type="table")

    # 3. Process images
    images_stored = 0
    for img_data in extracted.images:
        # Generate text description via vision LLM
        description = describe_image(img_data["bytes"], img_data["ext"])

        # Store raw bytes + metadata in SQLite
        image_id = store_image(
            company_id=company_id,
            role=role.value,
            img_bytes=img_data["bytes"],
            ext=img_data["ext"],
            page_num=img_data["page_num"],
            description=description,
        )

        # Embed the description into ChromaDB so images are semantically retrievable
        store_chunks(
            company_id,
            role.value,
            [f"[IMAGE:{image_id}] {description}"],
            chunk_type="image_description",
        )
        images_stored += 1

    return UploadResponse(
        message="PDF processed successfully",
        company_id=company_id,
        role=role,
        chunks_stored=chunks_stored,
        images_stored=images_stored,
    )


# ── Endpoint 2: Generate ──────────────────────────────────────────────────────

@app.post("/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest):

    # 1. Get all stored context for both companies
    sender_all = get_all_chunks(req.sender_id)
    receiver_all = get_all_chunks(req.receiver_id)

    if not sender_all or not receiver_all:
        raise HTTPException(
            status_code=404,
            detail=f"No context found for '{req.sender_id}' or '{req.receiver_id}'. Upload PDFs first."
        )

    # 2. Hybrid decision - full context or RAG
    sender_full_text = "\n\n".join(sender_all)
    receiver_full_text = "\n\n".join(receiver_all)
    total_tokens = estimate_tokens(sender_full_text + receiver_full_text)

    if total_tokens <= settings.rag_threshold_tokens:
        retrieval_mode = "full_context"
        sender_context = sender_full_text
        receiver_context = receiver_full_text
    else:
        retrieval_mode = "rag"
        sender_chunks = retrieve_chunks(req.sender_id, req.prompt, n_results=8)
        receiver_chunks = retrieve_chunks(req.receiver_id, req.prompt, n_results=8)
        sender_context = "\n\n".join(sender_chunks)
        receiver_context = "\n\n".join(receiver_chunks)

    # 3. Get image metadata for both companies
    sender_images = get_images_for_company(req.sender_id)
    receiver_images = get_images_for_company(req.receiver_id)

    # 4. Generate article
    try:
        article = generate_article(
            prompt=req.prompt,
            sender_id=req.sender_id,
            receiver_id=req.receiver_id,
            sender_context=sender_context,
            receiver_context=receiver_context,
            sender_images=sender_images,
            receiver_images=receiver_images,
            max_words=req.max_words,
            theme_color=req.theme_color,
            retrieval_mode=retrieval_mode,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Generation failed: {str(e)}")

    return GenerateResponse(
        article=article,
        retrieval_mode=retrieval_mode,
        context_tokens_estimated=total_tokens,
    )


# ── Image retrieval ───────────────────────────────────────────────────────────

@app.get("/image/{image_id}")
def get_image(image_id: str):
    """
    Fetch raw image bytes by UUID.
    The layout engine calls this to resolve image_placeholder IDs into actual files.
    """
    result = get_image_with_ext(image_id)
    if not result:
        raise HTTPException(status_code=404, detail="Image not found")
    img_bytes, ext = result
    media_type = f"image/{'jpeg' if ext in ('jpg', 'jpeg') else ext}"
    return Response(content=img_bytes, media_type=media_type)


# ── Companies ─────────────────────────────────────────────────────────────────

@app.get("/companies")
def companies():
    """List all companies that have been indexed, with chunk and image counts."""
    rows = list_companies()
    image_counts = get_image_counts()
    for row in rows:
        row["images"] = image_counts.get(row["company_id"], 0)
    return {"companies": rows}


# ── Delete company ────────────────────────────────────────────────────────────

@app.delete("/companies/{company_id}")
def delete_company_endpoint(company_id: str):
    deleted_vectors = delete_company(company_id)
    deleted_images = delete_company_images(company_id)
    if not deleted_vectors:
        raise HTTPException(status_code=404, detail=f"Company '{company_id}' not found")
    return {"deleted": company_id, "images_removed": deleted_images}


# ── Health check ──────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok"}