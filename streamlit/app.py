import streamlit as st
import requests
import json
import os
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
API_URL = os.getenv("API_URL") or st.secrets.get("API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Marketing Collateral Generator",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    [data-testid="InputInstructions"] { display: none !important; }
    [data-testid="baseButton-primary"],
    [data-testid="baseButton-primary"]:hover,
    [data-testid="baseButton-primary"]:active,
    [data-testid="baseButton-primary"]:focus {
        background-color: #E8360A !important;
        border-color: #E8360A !important;
        color: white !important;
        filter: none !important;
        transition: none !important;
    }
</style>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    with st.expander("What is this?"):
        st.markdown("""
**Marketing Collateral Generator** is an AutoGen-powered multi-agent system that produces
tailored B2B articles by reading the actual documents of both companies involved.

Upload PDFs for a **sender** (the company pitching) and a **receiver** (the target client).
The system extracts text, tables, and images, builds a vector index, then uses a Qwen LLM
via Groq to generate a structured, on-brand article - not a generic template.
""")

    with st.expander("How does it work?"):
        st.markdown("""
1. Upload PDFs for a sender and receiver company
2. Text, tables and images are extracted from each PDF
3. Images are described by a vision LLM (Qwen 3.8 27B)
4. Everything is embedded into a ChromaDB vector store, keyed by company ID
5. Generate a tailored article - full context or RAG depending on token volume
6. Output is structured JSON ready for a layout template
""")

    with st.expander("What is the stack?"):
        st.markdown("""
- **LLM** Qwen 3.8 27B via Groq
- **Vision** Qwen 3.8 27B via Groq
- **Embeddings** all-MiniLM-L6-v2
- **Vector store** ChromaDB
- **Image store** SQLite
- **API** FastAPI on Railway
""")

    st.divider()

    try:
        r = requests.get(f"{API_URL}/health", timeout=3)
        if r.status_code == 200:
            st.success("API connected")
        else:
            st.error("API error")
    except Exception:
        st.error(f"API unreachable: {API_URL}")

# ── Fetch companies ───────────────────────────────────────────────────────────
@st.cache_data(ttl=10)
def fetch_companies(api_url: str) -> list[dict]:
    try:
        r = requests.get(f"{api_url}/companies", timeout=5)
        if r.status_code == 200:
            return r.json().get("companies", [])
    except Exception:
        pass
    return []

# ── Title ─────────────────────────────────────────────────────────────────────
st.title("📰 Marketing Collateral Generator")
st.caption("Upload company PDFs, then generate a tailored B2B article.")

# ── Tabs ──────────────────────────────────────────────────────────────────────
companies_data = fetch_companies(API_URL)

tab_upload, tab_generate, tab_companies, tab_stack = st.tabs(["Upload", "Generate", "Indexed companies", "Stack"])

# ══════════════════════════════════════════
# UPLOAD TAB
# ══════════════════════════════════════════
with tab_upload:
    st.subheader("Upload company PDFs")
    st.caption(
        "**Sender** - the company pitching its product or service (e.g. an AI software vendor).  \n"
        "**Receiver** - the target client being addressed (e.g. a large logistics company).  \n"
        "**PDFs** - each document may contain text, tables and images; all are extracted and indexed.  \n"
        "**Company ID** - a short slug used to link uploaded context to article generation. Upload multiple PDFs under the same ID to enrich the index."
    )

    with st.form("upload_form"):
        company_id = st.text_input("Company ID", placeholder="e.g. acme-ai")
        role = st.radio("Role", options=["sender", "receiver"], horizontal=True)
        uploaded_files = st.file_uploader("PDF files", type=["pdf"], accept_multiple_files=True)
        submit_upload = st.form_submit_button("Load PDFs into system", type="primary", use_container_width=True)

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
                            files={"file": (pdf_file.name, pdf_file.getvalue(), "application/pdf")},
                            data={"company_id": company_id, "role": role},
                            timeout=120,
                        )
                        if response.status_code == 200:
                            data = response.json()
                            total_chunks += data["chunks_stored"]
                            total_images += data["images_stored"]
                        else:
                            errors.append(f"{pdf_file.name}: {response.json().get('detail', 'error')}")
                    except requests.exceptions.Timeout:
                        errors.append(f"{pdf_file.name}: timed out")
                    except Exception as e:
                        errors.append(f"{pdf_file.name}: {str(e)}")

            if errors:
                for err in errors:
                    st.error(err)
            else:
                st.success(
                    f"{len(uploaded_files)} PDF(s) processed for {company_id} ({role}) - "
                    f"{total_chunks} chunks embedded · {total_images} images stored"
                )
                fetch_companies.clear()

            if "uploads" not in st.session_state:
                st.session_state.uploads = []
            if not errors:
                entry = {"company_id": company_id, "role": role}
                if entry not in st.session_state.uploads:
                    st.session_state.uploads.append(entry)

    if st.session_state.get("uploads"):
        st.divider()
        st.caption("**Uploaded this session:**")
        for u in st.session_state.uploads:
            icon = "📤" if u["role"] == "sender" else "📥"
            st.markdown(f"{icon} `{u['company_id']}` - {u['role']}")

# ══════════════════════════════════════════
# GENERATE TAB
# ══════════════════════════════════════════
with tab_generate:
    st.subheader("Generate article")
    st.caption(
        "**Prompt** - describe the article angle; the LLM bridges the sender's offering with the receiver's industry context.  \n"
        "**Retrieval mode** - if the combined context fits within the token budget, full context is sent; otherwise RAG selects the most relevant passages per company.  \n"
        "**Constraints** - word limit, image placeholders and theme colour are enforced in the output JSON, ready to drop into a layout template.  \n"
        "**Output** - structured JSON with title, subtitle, sections, call-to-action and image references; downloadable for downstream rendering."
    )

    sender_ids   = [c["company_id"] for c in companies_data if c["role"] == "sender"]
    receiver_ids = [c["company_id"] for c in companies_data if c["role"] == "receiver"]
    all_ids      = [c["company_id"] for c in companies_data]

    with st.form("generate_form"):
        g_col1, g_col2 = st.columns(2)
        with g_col1:
            opts = sender_ids or all_ids
            if opts:
                sender_id = st.selectbox("Sender", opts)
            else:
                sender_id = st.text_input("Sender ID", placeholder="Upload a sender PDF first")
        with g_col2:
            opts = receiver_ids or all_ids
            if opts:
                receiver_id = st.selectbox("Receiver", opts)
            else:
                receiver_id = st.text_input("Receiver ID", placeholder="Upload a receiver PDF first")

        prompt = st.text_area(
            "Article topic",
            placeholder="e.g. How AI reduces last-mile delivery costs",
            height=80,
        )

        max_words = st.slider("Max words", 100, 600, 300, 50)

        submit_generate = st.form_submit_button("Generate article", type="primary", use_container_width=True)

    if submit_generate:
        if not sender_id or not receiver_id:
            st.error("Select both companies.")
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
                            "theme_color": "#E8360A",
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

    if "last_result" in st.session_state:
        result  = st.session_state["last_result"]
        article = result["article"]
        mode    = result["retrieval_mode"]
        tokens  = result["context_tokens_estimated"]

        st.divider()
        st.subheader("Output")

        tab_preview, tab_json = st.tabs(["Article preview", "Raw JSON"])

        with tab_preview:
            mode_label = "RAG retrieval" if mode == "rag" else "Full context"
            st.caption(f"{mode_label} · {article['word_count']} words · ~{tokens:,} context tokens")

            cta_color = article.get("theme_color", "#E8360A")
            st.markdown(f"## {article['title']}")
            st.markdown(f"*{article['subtitle']}*")
            st.divider()

            for section in article.get("sections", []):
                st.markdown(f"**{section['heading']}**")
                st.markdown(section["body"])

            if article.get("image_placeholders"):
                st.divider()
                st.markdown("**Images:**")
                for img in article["image_placeholders"]:
                    try:
                        img_response = requests.get(f"{API_URL}/image/{img['placeholder_id']}", timeout=10)
                        if img_response.status_code == 200:
                            st.image(img_response.content, caption=img["caption"], width=300)
                        else:
                            st.code(f"ID: {img['placeholder_id']} | {img['caption']}")
                    except Exception:
                        st.code(f"ID: {img['placeholder_id']} | {img['caption']}")

            st.divider()
            st.markdown("**Call to action:**")
            st.markdown(f"""
<div style="padding:12px 16px;border-radius:6px;font-weight:600;font-size:14px;color:white;background:{cta_color};">
    {article['call_to_action']}
</div>
""", unsafe_allow_html=True)
            st.markdown(" ")

        with tab_json:
            st.code(json.dumps(result, indent=2), language="json")

        st.divider()
        st.download_button(
            label="Download JSON",
            data=json.dumps(result, indent=2),
            file_name=f"article_{article['sender_id']}_{article['receiver_id']}_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
            mime="application/json",
        )

# ══════════════════════════════════════════
# INDEXED COMPANIES TAB
# ══════════════════════════════════════════
with tab_companies:
    st.subheader("Indexed companies")
    st.caption(
        "**Vector store** - each company's text and table chunks are embedded with `all-MiniLM-L6-v2` and stored in ChromaDB, keyed by company ID.  \n"
        "**Images** - extracted from PDFs, described by a vision LLM (Qwen 3.8 27B), and stored in SQLite; their descriptions are also embedded for semantic retrieval.  \n"
        "**Chunk counts** - text, table and image-description chunks are tracked separately so you can verify coverage before generating."
    )

    col_hdr, col_ref = st.columns([8, 1])
    with col_ref:
        if st.button("Refresh", key="_refresh_companies", use_container_width=True):
            fetch_companies.clear()
            st.rerun()

    if not companies_data:
        st.info("No companies indexed yet. Upload PDFs in the Upload tab to get started.")
    else:
        role_filter = st.selectbox(
            "Filter by role",
            ["All", "sender", "receiver"],
            key="_role_filter",
        )
        filtered = [c for c in companies_data if role_filter == "All" or c["role"] == role_filter]

        st.divider()
        for c in filtered:
            role_badge = "📤 sender" if c["role"] == "sender" else "📥 receiver"
            with st.container(border=True):
                c1, c2, c3, c4, c5 = st.columns([3, 2, 2, 2, 1])
                c1.markdown(f"**{c['company_id']}** &nbsp; {role_badge}")
                c2.metric("Text chunks", c["text_chunks"])
                c3.metric("Table chunks", c["table_chunks"])
                c4.metric("Images", c["images"])
                c5.markdown('<div style="margin-top:22px"></div>', unsafe_allow_html=True)
                if c5.button("🗑", key=f"_del_{c['company_id']}", help=f"Delete {c['company_id']}"):
                    try:
                        r = requests.delete(f"{API_URL}/companies/{c['company_id']}", timeout=10)
                        if r.status_code == 200:
                            st.success(f"{c['company_id']} deleted.")
                        else:
                            st.error(r.json().get("detail", "Delete failed"))
                    except Exception as e:
                        st.error(str(e))
                    fetch_companies.clear()
                    st.rerun()

# ══════════════════════════════════════════
# STACK TAB
# ══════════════════════════════════════════
with tab_stack:
    st.subheader("Local stack")
    st.caption(
        "This prototype runs fully locally. "
        "The AWS architecture deck shows the production-grade equivalent of each component."
    )
    st.divider()

    STACK = [
        {
            "layer": "API",
            "component": "FastAPI",
            "role": "REST layer exposing `/upload`, `/generate`, `/companies`, `/image`.",
            "aws_equiv": "API Gateway + Lambda",
        },
        {
            "layer": "PDF extraction",
            "component": "PyMuPDF",
            "role": "Extracts text blocks, tables (as Markdown), and raw image bytes from PDFs.",
            "aws_equiv": "Amazon Textract",
        },
        {
            "layer": "Embeddings",
            "component": "all-MiniLM-L6-v2",
            "role": "Encodes text and image descriptions into 384-dimensional vectors for semantic search.",
            "aws_equiv": "Amazon Bedrock - Titan Embeddings v2",
        },
        {
            "layer": "Vector store",
            "component": "ChromaDB",
            "role": "Stores and queries embedding vectors per company; supports full-context and RAG retrieval modes.",
            "aws_equiv": "Amazon OpenSearch Serverless",
        },
        {
            "layer": "Image store",
            "component": "SQLite",
            "role": "Persists raw image bytes and vision descriptions keyed by UUID.",
            "aws_equiv": "Amazon S3 + DynamoDB metadata",
        },
        {
            "layer": "Vision LLM",
            "component": "Qwen 3.8 27B via Groq",
            "role": "Generates a 2-3 sentence description of each extracted image for semantic indexing.",
            "aws_equiv": "Amazon Bedrock - Claude 3 Haiku (multimodal)",
        },
        {
            "layer": "Generation LLM",
            "component": "Qwen 3.8 27B via Groq",
            "role": "Produces a structured JSON article (title, sections, CTA, image refs) grounded in retrieved context.",
            "aws_equiv": "Amazon Bedrock - Claude 3 Sonnet",
        },
        {
            "layer": "Frontend",
            "component": "Streamlit",
            "role": "Upload, generate, and inspect indexed companies through a browser UI.",
            "aws_equiv": "React / Next.js on CloudFront + S3",
        },
    ]

    for item in STACK:
        with st.container(border=True):
            col_info, col_aws = st.columns([3, 2])
            with col_info:
                st.markdown(f"**{item['component']}**")
                st.caption(f"Layer: {item['layer']}")
                st.markdown(item["role"])
            with col_aws:
                st.markdown("**AWS equivalent**")
                st.caption(item["aws_equiv"])
