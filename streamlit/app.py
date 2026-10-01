import streamlit as st
import requests
import json
import os
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Marketing Collateral Generator",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    .section-header {
        font-size: 13px;
        font-weight: 600;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #E8360A;
        margin-bottom: 4px;
        margin-top: 24px;
    }
    .article-card {
        background: white;
        border-left: 4px solid #E8360A;
        border-radius: 0 8px 8px 0;
        padding: 28px 32px;
        margin-top: 16px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    }
    .article-title {
        font-size: 26px;
        font-weight: 700;
        color: #2C2C2C;
        margin-bottom: 6px;
        line-height: 1.2;
    }
    .article-subtitle {
        font-size: 15px;
        color: #888;
        margin-bottom: 24px;
        font-style: italic;
    }
    .article-section-heading {
        font-size: 16px;
        font-weight: 600;
        color: #2C2C2C;
        margin-top: 20px;
        margin-bottom: 6px;
    }
    .article-body {
        font-size: 15px;
        color: #444;
        line-height: 1.7;
        margin-bottom: 12px;
    }
    .article-cta {
        margin-top: 24px;
        padding: 12px 16px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 14px;
        color: white;
    }
    .image-chip {
        display: inline-block;
        background: #F0F0F0;
        border-radius: 4px;
        padding: 4px 10px;
        font-size: 12px;
        color: #555;
        margin-right: 6px;
        margin-top: 4px;
        font-family: monospace;
    }
    .meta-badge {
        display: inline-block;
        padding: 2px 10px;
        border-radius: 20px;
        font-size: 11px;
        font-weight: 600;
        margin-right: 6px;
    }
    .badge-rag { background: #FFF3CD; color: #856404; }
    .badge-full { background: #D1ECF1; color: #0C5460; }
    .badge-words { background: #F0F0F0; color: #555; }
    .upload-success {
        background: #F0FFF4;
        border: 1px solid #68D391;
        border-radius: 6px;
        padding: 12px 16px;
        font-size: 14px;
        color: #276749;
        margin-top: 8px;
    }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ML6 Challenge")
    st.markdown("**Automated B2B Marketing Collateral**")
    st.markdown("---")
    st.markdown("### How it works")
    st.markdown("""
1. Upload PDFs for a sender and receiver company
2. Text, tables and images are extracted
3. Images are described by a vision LLM
4. Everything is embedded into ChromaDB
5. Generate a tailored article — full context or RAG depending on token volume
6. Output is structured JSON ready for a layout template
    """)
    st.markdown("---")
    st.markdown("### Stack")
    st.markdown("""
- **LLM** Llama 3.3 70B via Groq
- **Vision** Llama 3.2 11B Vision
- **Embeddings** all-MiniLM-L6-v2
- **Vector store** ChromaDB
- **Image store** SQLite
- **API** FastAPI on Railway
    """)
    st.markdown("---")

    # API health check
    try:
        r = requests.get(f"{API_URL}/health", timeout=3)
        if r.status_code == 200:
            st.success("API connected")
        else:
            st.error("API error")
    except Exception:
        st.error(f"API unreachable: {API_URL}")

# ── Main header ───────────────────────────────────────────────────────────────
st.markdown("# Marketing Collateral Generator")
st.markdown("Upload company PDFs, then generate a tailored B2B article.")
st.markdown("---")

# ── Two columns ───────────────────────────────────────────────────────────────
col_upload, col_generate = st.columns([1, 1], gap="large")

# ══════════════════════════════════════════
# UPLOAD
# ══════════════════════════════════════════
with col_upload:
    st.markdown("### Step 1 — Upload company PDFs")

    with st.form("upload_form"):
        company_id = st.text_input(
            "Company ID",
            placeholder="e.g. acme-ai",
        )
        role = st.radio(
            "Role",
            options=["sender", "receiver"],
            horizontal=True,
        )
        uploaded_files = st.file_uploader(
            "PDF files",
            type=["pdf"],
            accept_multiple_files=True,
        )
        submit_upload = st.form_submit_button(
            "Upload PDFs",
            type="primary",
            use_container_width=True,
        )

    if submit_upload:
        if not company_id:
            st.error("Enter a company ID.")
        elif not uploaded_files:
            st.error("Select at least one PDF.")
        else:
            total_chunks = 0
            total_images = 0
            errors = []

            for pdf_file in uploaded_files:
                with st.spinner(f"Processing {pdf_file.name}…"):
                    try:
                        response = requests.post(
                            f"{API_URL}/upload",
                            files={
                                "file": (
                                    pdf_file.name,
                                    pdf_file.getvalue(),
                                    "application/pdf",
                                )
                            },
                            data={"company_id": company_id, "role": role},
                            timeout=120,
                        )
                        if response.status_code == 200:
                            data = response.json()
                            total_chunks += data["chunks_stored"]
                            total_images += data["images_stored"]
                        else:
                            errors.append(
                                f"{pdf_file.name}: {response.json().get('detail', 'error')}"
                            )
                    except requests.exceptions.Timeout:
                        errors.append(f"{pdf_file.name}: timed out")
                    except Exception as e:
                        errors.append(f"{pdf_file.name}: {str(e)}")

            if errors:
                for err in errors:
                    st.error(err)
            else:
                st.markdown(f"""
<div class="upload-success">
    ✓ <strong>{len(uploaded_files)} PDF(s)</strong> processed for
    <strong>{company_id}</strong> ({role})<br>
    {total_chunks} chunks embedded &nbsp;·&nbsp; {total_images} images stored
</div>
""", unsafe_allow_html=True)

            # Track uploads in session
            if "uploads" not in st.session_state:
                st.session_state.uploads = []
            if not errors:
                entry = {"company_id": company_id, "role": role}
                if entry not in st.session_state.uploads:
                    st.session_state.uploads.append(entry)

    if "uploads" in st.session_state and st.session_state.uploads:
        st.markdown("**Uploaded this session:**")
        for u in st.session_state.uploads:
            icon = "📤" if u["role"] == "sender" else "📥"
            st.markdown(f"{icon} `{u['company_id']}` — {u['role']}")

# ══════════════════════════════════════════
# GENERATE
# ══════════════════════════════════════════
with col_generate:
    st.markdown("### Step 2 — Generate article")

    with st.form("generate_form"):
        g_col1, g_col2 = st.columns(2)
        with g_col1:
            sender_id = st.text_input("Sender ID", placeholder="e.g. acme-ai")
        with g_col2:
            receiver_id = st.text_input("Receiver ID", placeholder="e.g. dhl-logistics")

        prompt = st.text_area(
            "Article topic",
            placeholder="e.g. How AI reduces last-mile delivery costs",
            height=80,
        )

        a_col1, a_col2 = st.columns(2)
        with a_col1:
            max_words = st.slider("Max words", 100, 600, 300, 50)
        with a_col2:
            theme_color = st.color_picker("Theme colour", value="#E8360A")

        submit_generate = st.form_submit_button(
            "Generate article",
            type="primary",
            use_container_width=True,
        )

    if submit_generate:
        if not sender_id or not receiver_id:
            st.error("Enter both company IDs.")
        elif not prompt:
            st.error("Enter an article topic.")
        else:
            with st.spinner("Generating article…"):
                try:
                    response = requests.post(
                        f"{API_URL}/generate",
                        json={
                            "sender_id": sender_id,
                            "receiver_id": receiver_id,
                            "prompt": prompt,
                            "max_words": max_words,
                            "theme_color": theme_color,
                        },
                        timeout=60,
                    )
                    if response.status_code == 200:
                        st.session_state["last_result"] = response.json()
                    else:
                        st.error(response.json().get("detail", "Generation failed"))

                except requests.exceptions.Timeout:
                    st.error("Request timed out. Try again.")
                except Exception as e:
                    st.error(f"Error: {str(e)}")

# ── Article output (full width) ───────────────────────────────────────────────
if "last_result" in st.session_state:
    result = st.session_state["last_result"]
    article = result["article"]
    mode = result["retrieval_mode"]
    tokens = result["context_tokens_estimated"]

    st.markdown("---")
    st.markdown("### Output")

    tab_preview, tab_json = st.tabs(["Article preview", "Raw JSON"])

    with tab_preview:
        badge_mode = "badge-rag" if mode == "rag" else "badge-full"
        mode_label = "RAG retrieval" if mode == "rag" else "Full context"
        st.markdown(f"""
<span class="meta-badge {badge_mode}">{mode_label}</span>
<span class="meta-badge badge-words">{article['word_count']} words</span>
<span class="meta-badge badge-words">~{tokens:,} context tokens</span>
""", unsafe_allow_html=True)

        # Article preview using native Streamlit components
        cta_color = article.get("theme_color", "#E8360A")

        st.markdown(f"## {article['title']}")
        st.markdown(f"*{article['subtitle']}*")
        st.divider()

        for section in article.get("sections", []):
            st.markdown(f"<span style='font-weight:700; color:{cta_color};'>{section['heading']}</span>", unsafe_allow_html=True)
            st.markdown(section['body'])

        if article.get("image_placeholders"):
            st.divider()
            st.markdown("**Images:**")
            for img in article["image_placeholders"]:
                try:
                    img_response = requests.get(
                        f"{API_URL}/image/{img['placeholder_id']}",
                        timeout=10,
                    )
                    if img_response.status_code == 200:
                        st.image(img_response.content, caption=img["caption"], width=300)
                    else:
                        st.code(f"ID: {img['placeholder_id']} | {img['caption']}")
                except Exception:
                    st.code(f"ID: {img['placeholder_id']} | {img['caption']}")

        st.divider()
        st.markdown(f"""
<div style="padding:12px 16px; border-radius:6px; font-weight:600; font-size:14px; color:white; background:{cta_color};">
    {article['call_to_action']}
</div>
""", unsafe_allow_html=True)
        st.markdown(" ")

    with tab_json:
        st.code(json.dumps(result, indent=2), language="json")

    st.download_button(
        label="Download JSON",
        data=json.dumps(result, indent=2),
        file_name=f"article_{article['sender_id']}_{article['receiver_id']}_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
        mime="application/json",
    )