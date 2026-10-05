# AWS Architecture Prep — Automated Marketing Collateral System

A study guide for the ML6 Senior AI Engineer interview. Covers every service in the proposed architecture, why it's there, and the trade-offs worth knowing.

---

## The Big Picture

The system exposes two REST endpoints:

- `POST /upload` — accepts PDFs for a sender + receiver company, extracts and indexes their content
- `POST /generate` — takes a prompt and returns a structured JSON article grounded in those PDFs

Both go through the same front door (API Gateway + Cognito), then branch into separate Lambda functions that each talk to a set of backend services.

---

## Service-by-Service Breakdown

### API Gateway

**What it is:** AWS's managed HTTP/REST API front door.

**What it does here:**
- Terminates TLS — your Lambda never deals with certificates
- Enforces rate limiting and throttling per API key (protects you from abuse and runaway costs)
- Validates request schemas before Lambda is even invoked (returns 400 for malformed payloads for free)
- Routes `/upload` and `/generate` to the Lambda orchestrator

**Key gotcha — file size limits:** API Gateway has a hard 10 MB payload limit. PDFs can easily exceed this. The cleaner pattern is to have the upload endpoint return a **presigned S3 URL** and let the client PUT the file directly to S3. This sidesteps the limit entirely and is cheaper (no Lambda invocation for the transfer itself).

**Trade-off worth knowing:** REST API vs HTTP API. HTTP API is cheaper and faster but lacks some features (no request validation, no API key throttling out of the box). For a production system, REST API is the safer choice here.

---

### Amazon Cognito

**What it is:** AWS's managed user identity and auth service.

**What it does here:**
- Issues JWTs (JSON Web Tokens) to authenticated callers
- API Gateway uses a **Cognito Authorizer** — it validates the JWT on every request automatically, no code required in Lambda
- The token payload carries the caller's identity; `sender_id` and `receiver_id` can be embedded as claims or passed as request parameters

**How the flow works:**
1. Client authenticates with Cognito → gets a JWT
2. Client includes JWT in the `Authorization: Bearer <token>` header
3. API Gateway calls Cognito to validate → passes or returns 401
4. Lambda receives the request only if auth passed

**Trade-off worth knowing:** For a B2B system where callers are other services (not end users), you'd likely use Cognito's **machine-to-machine (client credentials)** flow rather than username/password. Each customer gets a `client_id` and `client_secret`.

---

### AWS Lambda (Orchestrator + Workers)

**What it is:** Serverless compute — you deploy code, AWS runs it on demand, you pay per invocation.

**What it does here:** Three Lambda functions in total:

| Function | Trigger | Responsibility |
|---|---|---|
| Orchestrator | API Gateway | Parse `sender_id`/`receiver_id`, route to ingest or generate |
| Ingest worker | Orchestrator (or S3 event) | Call Textract, chunk text, generate embeddings, write to OpenSearch + S3 |
| Generate worker | Orchestrator | Query OpenSearch for context, call Bedrock LLM, return structured JSON |

**Key limits to know:**
- Max execution time: **15 minutes** (PDFs with many pages can push this — async pattern recommended for production)
- Max synchronous payload: **6 MB** in, **6 MB** out
- Memory: 128 MB to 10 GB (more memory = more CPU too)

**Core thing to understand about the 6 MB limit:** It only applies to what you pass into Lambda as its input argument — not what Lambda reads from other services during execution. So if Lambda receives an S3 event notification (just a tiny JSON pointer to the file), it can then stream the entire PDF from S3 without hitting the limit. The PDF bytes never count as Lambda's payload — only the trigger event does. This is why the S3 event pattern bypasses the size limitation entirely.

**Trade-off worth knowing:** Lambda vs Fargate. Lambda is simpler and cheaper for bursty, short workloads. Fargate (containers) is better when you need more control, longer runtimes, or consistent load. For the ingest path with large PDFs, Fargate is a reasonable alternative.

---

### Amazon Textract

**What it is:** AWS's managed OCR + document understanding service.

**What it does here:** Extracts text, tables, and layout structure from the input PDFs. This is important because the PDFs contain not just plain text but also tables and formatted content — a naive PDF parser (like PyPDF2) would miss table structure or mangle column order.

**Two modes:**
- **Synchronous** (`DetectDocumentText`) — for single-page or small documents, returns immediately
- **Asynchronous** (`StartDocumentAnalysis`) — for multi-page PDFs, returns a job ID; you poll or use SNS to get results

**Trade-off worth knowing:** Textract costs per page (~$0.0015/page for text detection). For high volume, cost adds up. Alternative: open-source tools like `pdfplumber` or `pymupdf` are free and fast but less accurate on complex layouts and scanned documents.

---

### Amazon Bedrock (Embeddings + LLM)

**What it is:** AWS's managed service for foundation models — you call an API, AWS handles the model infrastructure.

**What it does here — two separate uses:**

**1. Embeddings (ingest path)**
Converts text chunks into vector representations. These vectors capture semantic meaning, so "AI software for logistics" and "machine learning for supply chain" end up close together in vector space.
- Recommended model: **Amazon Titan Embeddings v2** or **Cohere Embed**
- Output: a 1536-dimensional float vector per chunk

**2. LLM generation (generate path)**
Takes the retrieved context chunks + the user's prompt and generates the article.
- Recommended model: **Claude 3 Sonnet or Haiku** (via Bedrock)
- Uses **structured output** — you pass a JSON schema and the model returns a valid JSON object (article title, body, word count, image tags, theme color etc.)

**Trade-off worth knowing:** Bedrock vs calling Anthropic/OpenAI directly. Bedrock keeps everything inside AWS (no data leaving your VPC if you use VPC endpoints), simplifies IAM-based access control, and gives you a single AWS bill. The downside: model availability lags behind the providers' direct APIs by weeks or months.

---

### Amazon OpenSearch Serverless (Vector Store)

**What it is:** A managed vector database built on OpenSearch, with no servers to provision — scales to zero when idle.

**What it does here:**
- Stores the embedding vectors produced during ingestion
- At query time, the generate Lambda sends the embedding of the user's prompt and gets back the top-k most semantically similar chunks (k-Nearest Neighbours search)
- Each document is namespaced by `sender_id` + `receiver_id` so queries only retrieve relevant company context

**How k-NN search works:** You're not searching by keyword — you're finding vectors that are geometrically close in 1536-dimensional space. "Close" = semantically similar.

**Trade-off worth knowing:** OpenSearch Serverless vs alternatives:
- **pgvector (Aurora/RDS)** — simpler if you already have a Postgres DB, good for moderate scale, but slower at large vector counts
- **Pinecone / Weaviate** — purpose-built, excellent performance, but outside AWS (data leaves your account)
- **OpenSearch Serverless** — native AWS, scales automatically, slightly more expensive at low volume but no ops overhead

---

### Amazon S3

**What it is:** Object storage — store any file, any size, pay for what you use.

**What it does here:**
- Stores the raw uploaded PDFs, organised by `sender_id/receiver_id/filename.pdf`
- Acts as the trigger point if using the presigned URL upload pattern (S3 event → Lambda ingest)
- Can also store generated articles for audit/replay

**Useful features here:**
- **Presigned URLs** — time-limited URLs that let a client upload directly without going through your API
- **S3 Event Notifications** — trigger a Lambda automatically when a new PDF lands in a specific prefix
- **Lifecycle policies** — automatically archive or delete old PDFs after N days to control costs

---

### Amazon DynamoDB

**What it is:** AWS's managed NoSQL key-value + document database. Single-digit millisecond latency.

**What it does here:**
- Stores metadata per company pair: which PDFs have been ingested, when, how many chunks, ingestion status
- Tracks async job status if using the background processing pattern
- Serves as the index the orchestrator checks before deciding whether context exists for a given `sender_id` + `receiver_id`

**Key design pattern:** Primary key = `sender_id#receiver_id`, sort key = `doc_id`. This lets you efficiently query all documents for a company pair.

**Trade-off worth knowing:** DynamoDB is great for simple key lookups. If you later need complex queries (filter by date range, full-text search on metadata), consider Aurora Serverless instead.

---

### CloudWatch + X-Ray + Secrets Manager

**CloudWatch:** Collects logs and metrics from every Lambda invocation automatically. You'd set alarms on error rate, latency, and Bedrock token usage.

**X-Ray:** Distributed tracing — lets you see the full journey of a single request across API Gateway → Lambda → Textract → Bedrock → OpenSearch, with timing at each hop. Essential for debugging latency issues.

**Secrets Manager:** Stores any API keys or credentials (e.g. if you call a third-party service). Lambdas retrieve secrets at runtime via IAM — no secrets hardcoded in environment variables.

---

## The Two Request Flows, Step by Step

### Upload flow

```
Client → API Gateway → Cognito auth → Lambda orchestrator
  → Ingest Lambda
    → Textract (extract text + tables from PDF)
    → Chunk text into ~500-token segments
    → Bedrock Embeddings (embed each chunk)
    → OpenSearch (store vectors with sender/receiver namespace)
    → S3 (store raw PDF)
    → DynamoDB (record ingestion metadata)
  → 200 OK
```

### Generate flow

```
Client → API Gateway → Cognito auth → Lambda orchestrator
  → Generate Lambda
    → Bedrock Embeddings (embed the user's prompt)
    → OpenSearch k-NN search (retrieve top-5 relevant chunks)
    → Bedrock LLM (Claude 3 + retrieved context + prompt → structured JSON)
    → DynamoDB (log the generation job)
  → 200 OK + JSON article
```

---

## Questions to Be Ready For

**"Why not just stuff the whole PDF into the LLM context?"**
Context windows have limits (and cost money per token). Chunking + retrieval means the LLM only sees the most relevant passages, keeping cost down and quality up. Also, with many company pairs, you'd quickly exceed any context window.

**"How do you handle large PDFs that take longer than Lambda's timeout?"**
Switch to async: the upload endpoint returns immediately with a `job_id`, Textract's async mode processes in the background, an SNS notification triggers the rest of the ingest Lambda when done. The client polls a `/status/{job_id}` endpoint.

**"How do you ensure the generated article is factually grounded?"**
The prompt instructs the LLM to only use information from the provided context chunks (retrieval-augmented generation). You can also add a verification step — a second LLM call that checks claims in the output against the source chunks.

**"What's the cost model?"**
Main cost drivers: Bedrock tokens (embedding + generation), Textract per-page pricing, OpenSearch Serverless OCU hours, and Lambda invocations. For a prototype, all of these are essentially free at low volume.

**"How would you scale this?"**
Lambda scales automatically. OpenSearch Serverless scales automatically. The main bottleneck at scale is Bedrock throughput limits (requests per minute) — you'd request a quota increase or implement a queue (SQS) in front of the generate Lambda to smooth out spikes.
