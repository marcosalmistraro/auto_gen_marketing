# ML6 Interview Notes & Talking Points

## LangChain vs Pydantic AI vs Pydantic

```
Pydantic          Pydantic AI          LangChain
"validate         "validate +          "do everything
 my output"        structured           for you"
                   LLM calls"
```

**Why we use plain Pydantic:**
> "I didn't use LangChain because for two endpoints the orchestration logic is simple enough to write explicitly. Every step is visible in the code — retrieval, prompt construction, LLM call, validation. There's nothing hidden in a framework abstraction."

Pydantic AI would be a slight step up — it wraps the LLM call and validation together in one step. Still simple, just less boilerplate. LangChain does all of that plus retrieval, memory, chaining, agents, tools — powerful but you lose visibility into what's actually happening.

For this use case plain Pydantic is the right level. The pipeline is simple enough that adding a framework would obscure more than it helps.

---

## PDF Extraction — Why PyMuPDF

Three main libraries exist: PyMuPDF, pdfplumber, pypdf.

| | PyMuPDF | pdfplumber | pypdf |
|---|---|---|---|
| Speed | Fastest | ~3× slower | Fast |
| Table detection | Native, good | Better for complex layouts | None |
| Image extraction | Yes, including inside tables | No | No |
| Mixed PDFs | Yes | Yes | Partial |

**Why PyMuPDF:**
> "The input PDFs contain text, tables and images. PyMuPDF is the only library that handles all three natively. pdfplumber has better table parsing for complex multi-column layouts but can't extract images and is significantly slower. pypdf has no table or image support at all."

**Why tables are serialized to Markdown and not CSV or JSON:**
> "LLMs read markdown tables natively — the row/column structure is preserved in a format the model can reason about directly. The embedding model also treats it as normal text, so it sits in the same vector space as everything else."

**Why images under 5KB are skipped:**
> "Small images are almost always decorative — bullets, icons, dividers. A 5KB threshold filters these out without any classification step. Real content images (logos, charts, photos) are consistently larger."

---

## Why SQLite for image storage

> "SQLite is zero infrastructure — it's a single file, ACID transactions, persists across restarts, queryable by company_id. For a prototype it's the right level. In production this maps cleanly to S3 for the raw bytes and RDS PostgreSQL for the metadata. The connection string is the only change."

**Why not store images in ChromaDB?**
ChromaDB stores vectors and text. Images are binary — they don't belong in a vector store. Separating them keeps each store doing what it's designed for.

**Why not store images on disk as files?**
SQLite keeps everything in one place — no file system management, no path handling, no risk of the bytes and the metadata getting out of sync. One database, one source of truth.

---

## Why ChromaDB for vector storage

> "ChromaDB bundles three things: an HNSW index for ANN search, a document store, and metadata filtering. The metadata filtering is what matters here — we need to filter by company_id at retrieval time. FAISS is just an index, it has no metadata layer, so we'd have to build that ourselves. ChromaDB gives it for free."

**Production migration path:**
ChromaDB → Amazon OpenSearch with k-NN plugin. Same query pattern, managed infrastructure, scales to billions of vectors.

---

## Two-layer LLM output validation

We enforce structured output at two layers:

**Layer 1 — Groq JSON mode:**
```python
response_format={"type": "json_object"}
```
Forces the model to return syntactically valid JSON. No markdown fences, no preamble, no "here is your article:". Guaranteed parseable.

**Layer 2 — Pydantic validation:**
```python
return ArticleJSON(**data)
```
Validates the JSON matches our schema. If the model hallucinated a field or dropped one, Pydantic raises a `ValidationError` immediately.

> "Either layer alone leaves a gap. JSON mode prevents unparseable responses but doesn't enforce the schema. Pydantic enforces the schema but only if the JSON is valid to begin with. Together they guarantee the layout engine always receives a well-formed article."

---

## Image descriptions vs multimodal embeddings (CLIP)

Two ways to make images searchable:

**Option A — Multimodal embeddings (CLIP)**
Embed images and text into a shared vector space directly. Images and text chunks live in the same index and can be retrieved together.

Problem: CLIP's image and text embedding spaces are aligned but not identical — retrieval quality degrades for business documents and logos. ChromaDB's cosine similarity also works better with a single consistent embedding space. Adds complexity to the retrieval layer.

**Option B — Vision LLM descriptions (our choice)**
Send each image to Llama 3.2 Vision at upload time, get back a text description. Embed the description as text alongside all other chunks.

> "Everything ends up in the same vector space — text, tables, and image descriptions are all embedded with the same MiniLM model. Retrieval logic stays simple. The descriptions are also human-readable so you can audit what the system understood about each image. The only cost is one extra LLM call per image at upload time, which is acceptable."

**When CLIP would be the right choice:**
If the use case required retrieving images by visual similarity — e.g. "find me images that look like this logo" — then multimodal embeddings would be necessary. For our use case we retrieve by semantic meaning, so text descriptions are sufficient.

---

## More notes to be added as we build...
