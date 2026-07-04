from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import DocumentRepository
from .embeddings import SentenceTransformerEmbeddingProvider
from .indexer import Indexer
from .rag import RagService
from .schemas import ChatRequest, SearchRequest
from .vector_store import VectorStore


app = FastAPI(title="Personal Knowledge Base API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def repository_service():
    settings = get_settings()
    repository = DocumentRepository(settings.sqlite_path)
    return settings, repository


def rag_services():
    settings, repository = repository_service()
    vector_store = VectorStore(settings.chroma_path)
    embeddings = SentenceTransformerEmbeddingProvider(settings.embedding_model)
    return settings, repository, vector_store, embeddings


def runtime_error(exc: Exception):
    raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/health")
def health():
    settings, repository = repository_service()
    chroma_count = 0
    vector_ready = True
    vector_error = ""
    try:
        vector_store = VectorStore(settings.chroma_path)
        chroma_count = vector_store.count()
    except Exception as exc:
        vector_ready = False
        vector_error = str(exc)

    return {
        "ok": True,
        "docs_root": str(settings.docs_root),
        "sqlite": str(repository.sqlite_path),
        "chroma_count": chroma_count,
        "vector_ready": vector_ready,
        "vector_error": vector_error,
        "openai_configured": bool(settings.openai_api_key),
    }


@app.post("/api/index/run")
def run_index():
    try:
        settings, repository, vector_store, embeddings = rag_services()
        return Indexer(settings.docs_root, repository, vector_store, embeddings).run()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        runtime_error(exc)


@app.get("/api/documents")
def list_documents():
    _, repository = repository_service()
    return {"documents": repository.list_documents()}


@app.get("/api/documents/{document_id}")
def get_document(document_id: str):
    _, repository = repository_service()
    document = repository.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


@app.post("/api/search")
def search(request: SearchRequest):
    try:
        settings, _, vector_store, embeddings = rag_services()
    except RuntimeError as exc:
        runtime_error(exc)
    rag = RagService(
        embeddings=embeddings,
        vector_store=vector_store,
        openai_api_key=settings.openai_api_key,
        openai_base_url=settings.openai_base_url,
        openai_model=settings.openai_model,
    )
    return {"results": rag.search(request.query, limit=request.limit)}


@app.post("/api/chat")
def chat(request: ChatRequest):
    try:
        settings, _, vector_store, embeddings = rag_services()
    except RuntimeError as exc:
        runtime_error(exc)
    rag = RagService(
        embeddings=embeddings,
        vector_store=vector_store,
        openai_api_key=settings.openai_api_key,
        openai_base_url=settings.openai_base_url,
        openai_model=settings.openai_model,
    )
    return rag.answer(request.question)
