from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


# ── Upload endpoint ──────────────────────────────────────────────────────────

class CompanyRole(str, Enum):
    sender = "sender"
    receiver = "receiver"


class UploadResponse(BaseModel):
    message: str
    company_id: str
    role: CompanyRole
    chunks_stored: int
    images_stored: int


# ── Generate endpoint ────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    sender_id: str = Field(..., description="ID of the sender company")
    receiver_id: str = Field(..., description="ID of the receiver company")
    prompt: str = Field(..., description="Topic or angle for the article")
    max_words: int = Field(300, description="Maximum words for the article body")
    theme_color: str = Field("#FF4500", description="Hex color for layout template")


class ImagePlaceholder(BaseModel):
    placeholder_id: str
    caption: str
    source_company: str


class ArticleSection(BaseModel):
    heading: str
    body: str


class ArticleJSON(BaseModel):
    title: str = Field(..., description="Article title, max 10 words")
    subtitle: str = Field(..., description="Article subtitle, max 20 words")
    sections: list[ArticleSection]
    call_to_action: str
    image_placeholders: list[ImagePlaceholder] = Field(default_factory=list)
    theme_color: str
    word_count: int
    sender_id: str
    receiver_id: str


class GenerateResponse(BaseModel):
    article: ArticleJSON
    retrieval_mode: str = Field(..., description="'full_context' or 'rag'")
    context_tokens_estimated: int
