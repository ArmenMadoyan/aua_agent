# System Overview — AUA Multi-Agent Q&A Platform

## What This Is

A multi-agent AI system that automates academic and administrative workflows at the American University of Armenia (AUA). Four specialized agents handle policy Q&A, course material generation, homework grading, and general chat — coordinated by a supervisor router.

---

## Architecture

```
User → Streamlit UI → FastAPI API → Supervisor Router → Agent
                                         │
                         ┌───────────────┼───────────────┐───────────────┐
                         ▼               ▼               ▼               ▼
                    KB Agent       Course Agent     Grading Agent    General Agent
                    (RAG)          (PPTX/PDF)       (Vision)         (Direct LLM)
                         │               │               │
                    ┌────┘          ┌────┘          ┌────┘
                    ▼               ▼               ▼
               PostgreSQL      File System      OpenAI Vision
              (embeddings)   (generated_course)   (GPT-4o)
```

### Supervisor Router
- Model: `gpt-4.1`, temperature `0`
- Structured output via Pydantic `_RouteDecision`
- Routes to: `general` | `kb` | `course` | `grading`
- Rules: latest user intent wins, attachment-aware, syllabus-aware
- Context: last 12 messages, user text capped at 4000 chars per message

### KB Agent (RAG)
- Model: `gpt-4.1`, temperature `0`
- Framework: LangChain `create_agent` with LangGraph
- Tool: `retrieve_from_knowledge_base` (top-5 retrieval)
- Data: 152 AUA policy PDFs
- System prompt enforces source citation (must name the PDF)

### Course Generation Agent
- Model: `gpt-4.1`, temperature `0.35`
- Framework: LangChain `create_agent` with LangGraph
- Tools: `create_powerpoint_deck`, `create_course_pdf`
- Syllabus injection into last user message (not system prompt)
- Outputs: PPTX via `python-pptx`, PDF via `fpdf2`
- Artifacts served at `/course/artifacts/{filename}`

### Grading Agent (Vision)
- Model: `gpt-4o` (configurable via `GRADING_VISION_MODEL`)
- Temperature: `0.2`
- Direct LLM stream (no tool-calling agent)
- Hardcoded output structure: `## Scores` + `## Feedback to student`
- PDF pages rasterized to PNG via PyMuPDF, 2x zoom, max 12 pages
- Max 24 vision items per message
- Only last user turn carries image attachments

### General Agent
- Model: `gpt-4.1`, temperature `0.2`
- Direct LLM stream
- Scoped to NOT perform RAG or generate files

---

## RAG Pipeline

```
152 PDFs → PyPDF text extraction → RecursiveCharacterTextSplitter → OpenAI embeddings → PostgreSQL
                                        (1000 chars, 200 overlap)      (1536-dim)       (double precision[])
```

- Embeddings: `OpenAIEmbeddings` (default `text-embedding-ada-002`, 1536 dimensions)
- Storage: PostgreSQL native `double precision[]` arrays — no `pgvector` extension
- Retrieval: application-layer cosine similarity in Python, brute-force over all chunks
- Default top-k: 3 (vector_store), overridden to 5 by KB agent tool
- Ingestion: automatic on startup, mtime-based change detection via `rag_state/ingestion_state.json`
- Deduplication: MD5 hash of document content (`doc_hash`)

---

## Context Management

- Conversation history stored in PostgreSQL (`conversations` + `messages` tables)
- LLM context window: sliding window of last 12 transcript entries sent to router
- Multimodal optimization: only the last user turn retains `attachments` and `model_content`; earlier turns reduced to display text only
- LangGraph checkpoints used for agent state persistence (tool outputs, partial results, routing decisions)

---

## Security and Guardrails

- Hardcoded grading output template prevents prompt injection
- Input validation:
  - Max 20 image attachments per request
  - Max 40 reference documents per request
  - Max 480K characters total reference text
  - Max 120K characters per individual reference document
  - Per-user text capped at 4000 chars in router context
- Context windowing: only last turn carries multimodal payload (cost + security)
- Routing isolation: each agent receives only relevant context

---

## Database Schema (PostgreSQL)

### `llm_models`
| Column | Type | Notes |
|--------|------|-------|
| id | serial PK | |
| model_id | text | unique, e.g. `gpt-4.1` |
| title | text | display name |
| is_default | boolean | default `false` |
| display_order | integer | default `0` |
| created_at | timestamptz | |
| updated_at | timestamptz | |

Seeded with: `('gpt-4.1', 'GPT-4.1', true, 0)`

### `conversations`
| Column | Type | Notes |
|--------|------|-------|
| id | serial PK | |
| user_id | integer | default `1` |
| title | text | nullable |
| created_at | timestamptz | |
| updated_at | timestamptz | |

### `messages`
| Column | Type | Notes |
|--------|------|-------|
| id | serial PK | |
| conversation_id | integer | FK → conversations.id, CASCADE |
| role | text | check: `user` or `assistant` |
| content | text | |
| agent_name | text | nullable (`general`, `kb`, `course`, `grading`) |
| agent_id | text | nullable |
| llm_model_id | integer | FK → llm_models.id, nullable |
| tools_called | jsonb | nullable, list of tool names |
| created_at | timestamptz | |

### `aua_policies`
| Column | Type | Notes |
|--------|------|-------|
| id | serial PK | |
| doc_hash | text | MD5 of source document, indexed |
| file_name | text | nullable |
| chunk_index | integer | default `0` |
| content | text | chunk text |
| embedding | float[] | check: `cardinality(embedding) = EMBEDDING_DIMENSION` |

---

## API Endpoints

### Chat (`/chat`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/chat/list` | List all chat sessions |
| POST | `/chat/get_messages` | Get messages for a chat |
| POST | `/chat/answer` | Ask a question (routes through orchestrator) |
| DELETE | `/chat/delete?chat_id=N` | Delete a chat session |

`/chat/answer` accepts:
- `chat_id`, `question`, `agent` (auto/general/kb/course/grading)
- `syllabus_text` (optional, for course agent)
- `attachments` (list of `{mime_type, base64}`, max 20)
- `reference_documents` (list of `{title, text}`, max 40)

### Knowledge (`/knowledge`)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/knowledge/list` | List document hashes |
| POST | `/knowledge/add` | Add document by text content |
| POST | `/knowledge/upload` | Upload a file |
| DELETE | `/knowledge/delete` | Delete by doc_hash |

---

## Tech Stack

| Component | Technology | Version |
|-----------|-----------|---------|
| Language | Python | 3.12 |
| Backend API | FastAPI | >=0.115 |
| Frontend | Streamlit | >=1.31 |
| Agent framework | LangChain + LangGraph | >=1.1 |
| LLM provider | OpenAI (GPT-4.1, GPT-4o) | API |
| Database | PostgreSQL | 16 |
| Migrations | Alembic | >=1.13 |
| ORM/DB driver | psycopg 3 + SQLAlchemy | >=3.2 / >=2.0 |
| PDF extraction | PyPDF | >=6.9 |
| PDF rasterization | PyMuPDF | >=1.24 |
| PPTX generation | python-pptx | >=1.0 |
| PDF generation | fpdf2 | >=2.8 |
| DOCX parsing | python-docx | >=1.1 |
| Text splitting | langchain_text_splitters | 1.1 |
| Env management | python-dotenv | 1.2 |

---

## LLM Models Used

| Model | Role | Temperature | Price (Input/Output per MTok) |
|-------|------|-------------|-------------------------------|
| gpt-4.1 | Router, KB agent, Course agent, General agent | 0 / 0 / 0.35 / 0.2 | $2.00 / $8.00 |
| gpt-4o | Grading agent (vision) | 0.2 | $2.50 / $10.00 |
| OpenAI Embeddings | RAG embeddings (1536-dim) | N/A | ~$0.10 / MTok |

Models evaluated but not used in production:
| Model | Notes |
|-------|-------|
| Claude Sonnet 4 | Better structured prose, higher cost ($3.00/$15.00), slower |
| Gemini 2.5 Flash | Cheapest ($0.30/$2.50), good for LLM-as-a-judge, weaker on structured tasks |

---

## Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENAI_API_KEY` | Yes | — | OpenAI API key |
| `DATABASE_URL` | Yes | — | PostgreSQL connection URL |
| `EMBEDDING_DIMENSION` | No | `1536` | Must match embedding model output |
| `DEFAULT_USER_ID` | No | `1` | Default user ID for new sessions |
| `GRADING_VISION_MODEL` | No | `gpt-4o` | Vision model for grading agent |

---

## Deployment

- **Docker:** Multi-stage Dockerfile with `backend` and `frontend` targets
- **docker-compose.yml:** PostgreSQL 16 + FastAPI + Streamlit, all wired together
- **Local dev:**
  - `uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000`
  - `streamlit run frontend/app.py`
  - `alembic upgrade head` (or auto-runs on startup via `init_db()`)

---

## Project Structure

```
capstone_agentic_research/
├── ai/
│   ├── __init__.py
│   ├── agents.py              # KB and Course LangGraph agents
│   ├── chat_context.py        # Last-turn-only multimodal optimization
│   ├── config.py              # API key, grading model env vars
│   ├── course_builders.py     # PPTX and PDF file generation
│   ├── course_output.py       # Output paths, artifact URLs
│   ├── course_tools.py        # LangChain tools for course agent
│   ├── document_text.py       # Text extraction (txt/pdf/docx), reference merging
│   ├── grading.py             # Grading system prompt, multimodal message builder
│   ├── grading_media.py       # PDF rasterization, image processing
│   ├── orchestrator.py        # Router + agent dispatch + streaming
│   ├── tools.py               # RAG search tool
│   ├── upload_bundle.py       # File upload processing for Streamlit
│   ├── vector_store.py        # Embedding, storage, cosine search, ingestion
│   └── fonts/
│       └── DejaVuSans.ttf
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── 0001_initial_schema.py
├── backend/
│   ├── __init__.py
│   ├── app.py                 # FastAPI app, startup events
│   ├── db.py                  # PostgreSQL operations
│   └── routers/
│       ├── __init__.py
│       ├── chat.py            # Chat API endpoints
│       └── knowledge.py       # Knowledge base API endpoints
├── frontend/
│   └── app.py                 # Streamlit UI
├── paper/
│   ├── main.tex               # IEEE conference paper (LaTeX)
│   └── main.pdf               # Compiled paper
├── aua_policy_pdfs/           # 152 AUA policy PDF documents
├── generated_course/          # Generated PPTX/PDF artifacts
├── rag_state/                 # Ingestion state tracking
├── alembic.ini
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
├── .env.example
├── .gitignore
├── Makefile
└── README.md
```

---

## Key Hardcoded Values

| Value | Location | Purpose |
|-------|----------|---------|
| `1000` chars / `200` overlap | `vector_store.py` | Chunk size for text splitting |
| `1536` | `db.py` default | Embedding dimension |
| `5` | `tools.py` | RAG top-k retrieval |
| `12` messages | `orchestrator.py` | Router transcript window |
| `4000` chars | `orchestrator.py` | Per-message text cap for router |
| `12` pages | `grading_media.py` | Max PDF pages for vision |
| `2.0` zoom | `grading_media.py` | PDF rasterization quality |
| `24` items | `upload_bundle.py` | Max vision items per message |
| `220` chars | `upload_bundle.py` | Scanned PDF detection threshold |
| `80,000` chars | `upload_bundle.py` | Extracted text trim limit |
| `120,000` chars | `document_text.py` | Max reference block size |
| `480,000` chars | `chat.py` | Max combined reference documents |
| `20` | `chat.py` | Max attachment images per request |
| `40` | `chat.py` | Max reference documents per request |
| `48` chars | `course_output.py` | Max filename stem length |
