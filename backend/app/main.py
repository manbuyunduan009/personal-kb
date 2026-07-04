import time

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import DocumentRepository
from .embeddings import create_embedding_provider
from .indexer import Indexer
from .product_expert import analyze_requirement_change, build_requirement_card, group_documents_by_requirement
from .rag import RagService
from .schemas import ChangeAnalysisRequest, ChatRequest, FeedbackRequest, SearchRequest
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
    vector_store = VectorStore(settings.vector_sqlite_path)
    embeddings = create_embedding_provider(settings.embedding_provider, settings.embedding_model)
    return settings, repository, vector_store, embeddings


def runtime_error(exc: Exception):
    raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/health")
def health():
    settings, repository = repository_service()
    chunk_count = 0
    vector_ready = True
    vector_error = ""
    try:
        vector_store = VectorStore(settings.vector_sqlite_path)
        chunk_count = vector_store.count()
    except Exception as exc:
        vector_ready = False
        vector_error = str(exc)

    return {
        "ok": True,
        "docs_root": str(settings.docs_root),
        "sqlite": str(repository.sqlite_path),
        "vector_store": str(settings.vector_sqlite_path),
        "embedding_provider": settings.embedding_provider,
        "embedding_model": settings.embedding_model,
        "chunk_count": chunk_count,
        "chroma_count": chunk_count,
        "vector_ready": vector_ready,
        "vector_error": vector_error,
        "openai_configured": bool(settings.openai_api_key),
        "min_evidence_score": settings.min_evidence_score,
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
        settings, repository, vector_store, embeddings = rag_services()
    except RuntimeError as exc:
        runtime_error(exc)
    rag = RagService(
        embeddings=embeddings,
        vector_store=vector_store,
        openai_api_key=settings.openai_api_key,
        openai_base_url=settings.openai_base_url,
        openai_model=settings.openai_model,
        feedback_scores=repository.feedback_scores(),
        min_evidence_score=settings.min_evidence_score,
    )
    return {"results": rag.search(request.query, limit=request.limit)}


@app.post("/api/chat")
def chat(request: ChatRequest):
    try:
        settings, repository, vector_store, embeddings = rag_services()
    except RuntimeError as exc:
        runtime_error(exc)
    rag = RagService(
        embeddings=embeddings,
        vector_store=vector_store,
        openai_api_key=settings.openai_api_key,
        openai_base_url=settings.openai_base_url,
        openai_model=settings.openai_model,
        feedback_scores=repository.feedback_scores(),
        min_evidence_score=settings.min_evidence_score,
    )
    start = time.perf_counter()
    result = rag.answer(request.question)
    latency_ms = int((time.perf_counter() - start) * 1000)
    trace = repository.add_rag_trace(request.question, result, latency_ms)
    result["trace_id"] = trace["id"]
    return result


@app.post("/api/feedback")
def create_feedback(request: FeedbackRequest):
    _, repository = repository_service()
    feedback = repository.add_feedback(
        question=request.question,
        source_path=request.source_path,
        chunk_index=request.chunk_index,
        chunk_header=request.chunk_header,
        rating=request.rating,
        note=request.note,
    )
    return {"ok": True, "feedback": feedback}


@app.get("/api/feedback/summary")
def feedback_summary():
    _, repository = repository_service()
    return {"summary": repository.feedback_summary()}


@app.get("/api/traces")
def list_rag_traces(limit: int = Query(default=20, ge=1, le=100)):
    _, repository = repository_service()
    return {"traces": repository.list_rag_traces(limit=limit)}


@app.get("/api/product/requirements")
def list_product_requirements():
    _, repository = repository_service()
    return {"requirements": group_documents_by_requirement(repository.list_documents())}


@app.get("/api/product/requirements/{requirement_key}/card")
def get_product_requirement_card(requirement_key: str):
    _, repository = repository_service()
    documents = repository.list_documents()
    try:
        return build_requirement_card(requirement_key, documents)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Requirement not found") from exc


@app.post("/api/product/change-analysis")
def analyze_product_change(request: ChangeAnalysisRequest):
    _, repository = repository_service()
    old_document = repository.get_document(request.old_document_id)
    new_document = repository.get_document(request.new_document_id)
    if old_document is None:
        raise HTTPException(status_code=404, detail="Old document not found")
    if new_document is None:
        raise HTTPException(status_code=404, detail="New document not found")
    return analyze_requirement_change(old_document, new_document)
