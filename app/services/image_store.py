import sqlite3
import uuid
from app.config import settings


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.sqlite_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables on startup if they don't exist."""
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS images (
                id          TEXT PRIMARY KEY,
                company_id  TEXT NOT NULL,
                role        TEXT NOT NULL,
                description TEXT,
                ext         TEXT NOT NULL,
                page_num    INTEGER,
                raw_bytes   BLOB NOT NULL,
                created_at  DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_company ON images(company_id)"
        )
        conn.commit()


def store_image(
    company_id: str,
    role: str,
    img_bytes: bytes,
    ext: str,
    page_num: int,
    description: str = "",
) -> str:
    """Store image, return its UUID."""
    image_id = str(uuid.uuid4())
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO images
                (id, company_id, role, description, ext, page_num, raw_bytes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (image_id, company_id, role, description, ext, page_num, img_bytes),
        )
        conn.commit()
    return image_id


def get_images_for_company(company_id: str) -> list[dict]:
    """Get all image metadata for a company — no raw bytes."""
    with _get_conn() as conn:
        rows = conn.execute(
            """
            SELECT id, company_id, role, description, ext, page_num
            FROM images
            WHERE company_id = ?
            """,
            (company_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def delete_company_images(company_id: str) -> int:
    """Delete all images for a company. Returns count deleted."""
    with _get_conn() as conn:
        cur = conn.execute("DELETE FROM images WHERE company_id = ?", (company_id,))
        conn.commit()
    return cur.rowcount


def get_image_counts() -> dict[str, int]:
    """Return {company_id: image_count} for all companies."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT company_id, COUNT(*) as cnt FROM images GROUP BY company_id"
        ).fetchall()
    return {row["company_id"]: row["cnt"] for row in rows}


def get_image_with_ext(image_id: str) -> tuple[bytes, str] | None:
    """Fetch raw bytes and file extension for a specific image by ID."""
    with _get_conn() as conn:
        row = conn.execute(
            "SELECT raw_bytes, ext FROM images WHERE id = ?",
            (image_id,),
        ).fetchone()
    return (row["raw_bytes"], row["ext"]) if row else None