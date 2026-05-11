"""PGVectorStore-backed document storage, embedding, and retrieval."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List

from langchain_openai import OpenAIEmbeddings
from langchain_postgres import PGVector
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from backend.config import DATABASE_URL, OPENAI_API_KEY

BASE_DIR = Path(__file__).resolve().parent.parent.parent

AUA_POLICY_PDFS_DIR = BASE_DIR / "aua_policy_pdfs"
RAG_STATE_DIR = BASE_DIR / "rag_state"
INGESTION_STATE_FILE = RAG_STATE_DIR / "ingestion_state.json"

COLLECTION_NAME = "aua_policies"

embeddings = OpenAIEmbeddings(openai_api_key=OPENAI_API_KEY)

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200,
    length_function=len,
)


def _pg_connection_string() -> str:
    url = DATABASE_URL
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _get_vector_store() -> PGVector:
    return PGVector(
        embeddings=embeddings,
        collection_name=COLLECTION_NAME,
        connection=_pg_connection_string(),
        use_jsonb=True,
    )


def _get_content_hash(content: str) -> str:
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def add_document(content: str, file_name: str | None = None) -> str:
    doc_hash = _get_content_hash(content)
    display_name = file_name or f"doc_{doc_hash[:8]}.txt"

    delete_document(doc_hash)

    chunks = text_splitter.split_text(content)
    if not chunks:
        return doc_hash

    metadatas = [
        {"doc_hash": doc_hash, "file_name": display_name, "chunk_index": i}
        for i in range(len(chunks))
    ]

    store = _get_vector_store()
    store.add_texts(texts=chunks, metadatas=metadatas)

    return doc_hash


def search(query: str, k: int = 3) -> List[dict]:
    store = _get_vector_store()
    docs = store.similarity_search_with_score(query, k=k)

    return [
        {
            "content": doc.page_content,
            "source": doc.metadata.get("file_name", "unknown"),
            "score": float(score),
        }
        for doc, score in docs
    ]


def _extract_text_from_pdf(pdf_path: Path) -> str:
    try:
        reader = PdfReader(str(pdf_path))
        parts = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                parts.append(text)
        return "\n\n".join(parts).strip() if parts else ""
    except Exception as e:
        print(f"Error extracting text from {pdf_path}: {e}")
        return ""


def _load_ingestion_state() -> Dict[str, dict]:
    if not INGESTION_STATE_FILE.exists():
        return {}
    try:
        data = json.loads(INGESTION_STATE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_ingestion_state(state: Dict[str, dict]) -> None:
    RAG_STATE_DIR.mkdir(parents=True, exist_ok=True)
    INGESTION_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def load_existing_files() -> None:
    if not AUA_POLICY_PDFS_DIR.exists():
        print(f"AUA policy PDFs directory not found: {AUA_POLICY_PDFS_DIR}")
        return

    state = _load_ingestion_state()
    updated = False

    for file_path in sorted(AUA_POLICY_PDFS_DIR.glob("*.pdf")):
        try:
            mtime = file_path.stat().st_mtime
            name = file_path.name
            if name in state and state[name].get("mtime") == mtime:
                continue
            content = _extract_text_from_pdf(file_path)
            if not content or not content.strip():
                print(f"Skipping {file_path.name}: no text extracted")
                continue
            doc_hash = add_document(content, file_name=name)
            state[name] = {"mtime": mtime, "doc_hash": doc_hash}
            updated = True
        except Exception as e:
            print(f"Error loading {file_path}: {e}")

    if updated:
        _save_ingestion_state(state)


def delete_document(doc_hash: str) -> bool:
    store = _get_vector_store()
    try:
        collection = store.get_collection(store._session)  # type: ignore[attr-defined]
        if collection is None:
            return False
    except Exception:
        pass

    from sqlalchemy import text as sa_text
    from sqlalchemy import create_engine

    engine = create_engine(_pg_connection_string())
    with engine.connect() as conn:
        result = conn.execute(
            sa_text(
                "DELETE FROM langchain_pg_embedding "
                "WHERE cmetadata->>'doc_hash' = :dh "
                "AND collection_id = ("
                "  SELECT uuid FROM langchain_pg_collection "
                "  WHERE name = :cname"
                ")"
            ),
            {"dh": doc_hash, "cname": COLLECTION_NAME},
        )
        conn.commit()
        deleted = result.rowcount > 0

    if deleted:
        state = _load_ingestion_state()
        for name, info in list(state.items()):
            if info.get("doc_hash") == doc_hash:
                del state[name]
                _save_ingestion_state(state)
                break
    return deleted


def document_exists(doc_hash: str) -> bool:
    from sqlalchemy import text as sa_text
    from sqlalchemy import create_engine

    engine = create_engine(_pg_connection_string())
    with engine.connect() as conn:
        result = conn.execute(
            sa_text(
                "SELECT 1 FROM langchain_pg_embedding "
                "WHERE cmetadata->>'doc_hash' = :dh "
                "AND collection_id = ("
                "  SELECT uuid FROM langchain_pg_collection "
                "  WHERE name = :cname"
                ") LIMIT 1"
            ),
            {"dh": doc_hash, "cname": COLLECTION_NAME},
        )
        return result.fetchone() is not None


def list_documents() -> List[str]:
    from sqlalchemy import text as sa_text
    from sqlalchemy import create_engine

    engine = create_engine(_pg_connection_string())
    with engine.connect() as conn:
        result = conn.execute(
            sa_text(
                "SELECT DISTINCT cmetadata->>'doc_hash' AS dh "
                "FROM langchain_pg_embedding "
                "WHERE collection_id = ("
                "  SELECT uuid FROM langchain_pg_collection "
                "  WHERE name = :cname"
                ") ORDER BY dh"
            ),
            {"cname": COLLECTION_NAME},
        )
        return [row[0] for row in result if row[0]]
