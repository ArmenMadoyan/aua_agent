import hashlib
import json
from pathlib import Path
from typing import Dict, List, Sequence

from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from ai.config import API_KEY
from backend.db import EMBEDDING_DIMENSION, get_connection

BASE_DIR = Path(__file__).resolve().parent.parent

AUA_POLICY_PDFS_DIR = BASE_DIR / "aua_policy_pdfs"
RAG_STATE_DIR = BASE_DIR / "rag_state"
INGESTION_STATE_FILE = RAG_STATE_DIR / "ingestion_state.json"

embeddings = OpenAIEmbeddings(openai_api_key=API_KEY)

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1000,
    chunk_overlap=200,
    length_function=len,
)


def _get_content_hash(content: str) -> str:
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def _cosine_distance(a: Sequence[float], b: Sequence[float]) -> float:
    """1 - cosine similarity; lower means more similar."""
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 1.0
    return 1.0 - (dot / (na * nb))


def add_document(content: str, file_name: str = None) -> str:
    doc_hash = _get_content_hash(content)

    chunks = text_splitter.split_text(content)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM aua_policies WHERE doc_hash = %s", (doc_hash,))

            if not chunks:
                return doc_hash

            chunk_embeddings = embeddings.embed_documents(chunks)
            display_name = file_name or f"doc_{doc_hash[:8]}.txt"

            for i, (chunk, emb) in enumerate(zip(chunks, chunk_embeddings)):
                if len(emb) != EMBEDDING_DIMENSION:
                    raise ValueError(
                        f"Embedding length {len(emb)} != EMBEDDING_DIMENSION {EMBEDDING_DIMENSION}"
                    )
                cur.execute(
                    """
                    INSERT INTO aua_policies (doc_hash, file_name, chunk_index, content, embedding)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (doc_hash, display_name, i, chunk, emb),
                )

    return doc_hash


def search(query: str, k: int = 3) -> List[dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT content, file_name, embedding FROM aua_policies",
            )
            rows = cur.fetchall()

    if not rows:
        return []

    query_embedding = embeddings.embed_query(query)
    if len(query_embedding) != EMBEDDING_DIMENSION:
        raise ValueError(
            f"Query embedding length {len(query_embedding)} != EMBEDDING_DIMENSION {EMBEDDING_DIMENSION}"
        )

    scored: list[tuple[float, dict]] = []
    for row in rows:
        emb = row["embedding"]
        dist = _cosine_distance(query_embedding, emb)
        scored.append(
            (
                dist,
                {
                    "content": row["content"],
                    "file_name": row["file_name"],
                },
            )
        )

    scored.sort(key=lambda x: x[0])
    limit = min(k, len(scored))
    return [
        {
            "content": item[1]["content"],
            "source": item[1]["file_name"] or "unknown",
            "score": item[0],
        }
        for item in scored[:limit]
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
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM aua_policies WHERE doc_hash = %s", (doc_hash,))
            deleted = cur.rowcount > 0

    if deleted:
        state = _load_ingestion_state()
        for name, info in list(state.items()):
            if info.get("doc_hash") == doc_hash:
                del state[name]
                _save_ingestion_state(state)
                break
    return deleted


def document_exists(doc_hash: str) -> bool:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM aua_policies WHERE doc_hash = %s LIMIT 1",
                (doc_hash,),
            )
            return cur.fetchone() is not None


def list_documents() -> List[str]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT doc_hash FROM aua_policies
                ORDER BY doc_hash
                """
            )
            rows = cur.fetchall()
    return [row["doc_hash"] for row in rows]
