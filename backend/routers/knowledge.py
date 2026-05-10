import hashlib

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from ai.vector_store import add_document, delete_document, list_documents, document_exists

knowledge_router = APIRouter(prefix="/knowledge", tags=["knowledge"])


class DocumentListResponse(BaseModel):
    documents: list[str]


class DeleteDocumentRequest(BaseModel):
    doc_hash: str


class AddDocumentRequest(BaseModel):
    content: str
    file_name: str = None  # Optional, for display purposes only


class DeleteDocumentResponse(BaseModel):
    success: bool
    message: str


class DocumentResponse(BaseModel):
    success: bool
    doc_hash: str
    is_duplicate: bool


@knowledge_router.get("/list", response_model=DocumentListResponse)
def list_knowledge_documents():
    documents = list_documents()
    return {"documents": documents}


@knowledge_router.post("/add", response_model=DocumentResponse)
def add_document_endpoint(payload: AddDocumentRequest):
    try:
        doc_hash = hashlib.md5(payload.content.encode('utf-8')).hexdigest()
        is_duplicate = document_exists(doc_hash)

        add_document(payload.content, file_name=payload.file_name)

        return {
            "success": True,
            "doc_hash": doc_hash,
            "is_duplicate": is_duplicate
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error adding document: {str(e)}"
        )


@knowledge_router.post("/upload", response_model=DocumentResponse)
async def upload_document(file: UploadFile = File(...)):
    try:
        content = await file.read()
        content_str = content.decode('utf-8')

        doc_hash = hashlib.md5(content_str.encode('utf-8')).hexdigest()
        is_duplicate = document_exists(doc_hash)

        add_document(content_str, file_name=file.filename)

        return {
            "success": True,
            "doc_hash": doc_hash,
            "is_duplicate": is_duplicate
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error uploading document: {str(e)}"
        )


@knowledge_router.delete("/delete", response_model=DeleteDocumentResponse)
def delete_knowledge_document(payload: DeleteDocumentRequest):
    doc_hash = payload.doc_hash

    deleted = delete_document(doc_hash)

    if not deleted:
        raise HTTPException(
            status_code=404,
            detail=f"Document with hash '{doc_hash}' not found in knowledge base"
        )

    return {
        "success": True,
        "message": f"Document with hash '{doc_hash}' deleted successfully"
    }
