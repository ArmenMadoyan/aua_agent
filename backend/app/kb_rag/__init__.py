"""Knowledge-base RAG: vector store, embeddings, and document ingestion."""

from backend.app.kb_rag.vector_store import (
    add_document,
    delete_document,
    document_exists,
    list_documents,
    load_existing_files,
    search,
)

__all__ = [
    "add_document",
    "delete_document",
    "document_exists",
    "list_documents",
    "load_existing_files",
    "search",
]
