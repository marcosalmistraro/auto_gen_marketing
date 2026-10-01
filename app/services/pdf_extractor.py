import fitz  # PyMuPDF
import base64
from dataclasses import dataclass, field


@dataclass
class ExtractedPDF:
    text_blocks: list[str] = field(default_factory=list)   # plain text per page
    table_blocks: list[str] = field(default_factory=list)  # tables as markdown
    images: list[dict] = field(default_factory=list)       # {bytes, ext, page_num}


def extract_pdf(file_bytes: bytes) -> ExtractedPDF:
    """
    Extract all content from a PDF.

    Why PyMuPDF over pdfplumber or pypdf?
    - Fastest of the three
    - Best native table detection
    - Extracts embedded images including those inside tables
    - Handles both text-based and mixed PDFs
    """
    result = ExtractedPDF()
    doc = fitz.open(stream=file_bytes, filetype="pdf")

    for page_num, page in enumerate(doc):

        # ── Text ──────────────────────────────────────────────────────────────
        text = page.get_text("text").strip()
        if text:
            result.text_blocks.append(text)

        # ── Tables ────────────────────────────────────────────────────────────
        # PyMuPDF detects table bounding boxes and extracts cell text
        # We serialize to markdown so it embeds as readable prose
        tabs = page.find_tables()
        for tab in tabs.tables:
            md = _table_to_markdown(tab.extract())
            if md:
                result.table_blocks.append(md)

        # ── Images ────────────────────────────────────────────────────────────
        for img_ref in page.get_images(full=True):
            xref = img_ref[0]
            base_image = doc.extract_image(xref)
            img_bytes = base_image["image"]
            ext = base_image["ext"]

            # Skip tiny images — icons, bullets, decorations
            # Threshold: 5KB
            if len(img_bytes) < 5000:
                continue

            result.images.append({
                "bytes": img_bytes,
                "ext": ext,
                "page_num": page_num,
            })

    doc.close()
    return result


def _table_to_markdown(rows: list[list]) -> str:
    """
    Convert a list-of-lists table to markdown.

    Why markdown and not CSV or JSON?
    - LLMs read markdown tables natively
    - Preserves row/column structure in a human-readable format
    - Embedding model treats it as normal text
    """
    if not rows:
        return ""

    cleaned = [
        [str(cell).strip() if cell is not None else "" for cell in row]
        for row in rows
    ]

    header = cleaned[0]
    separator = ["---"] * len(header)
    body = cleaned[1:]

    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def image_to_base64(img_bytes: bytes, ext: str) -> str:
    """Convert raw image bytes to base64 for vision LLM API calls."""
    return base64.b64encode(img_bytes).decode("utf-8")
