"""Document ingestion, upload, search, and context endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from src.api.deps import get_cache, get_storage
from src.api.models import (
    ContextResponse,
    IngestRequest,
    IngestResponse,
    SearchResult,
    TopicsResponse,
    UploadResponse,
)
from src.cache import BodhiCache
from src.rag import extract_topics, ingest_document, retrieve_context
from src.storage import BodhiStorage

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/ingest", response_model=IngestResponse)
async def ingest_text(
    body: IngestRequest,
    storage: BodhiStorage = Depends(get_storage),
):
    n = ingest_document(
        company=body.company,
        role=body.role,
        text=body.text,
        storage=storage,
        source_label=body.source_label,
    )
    return IngestResponse(chunks_ingested=n)


@router.post("/upload", response_model=UploadResponse)
async def upload_file(
    company: str = Form(...),
    role: str = Form("general"),
    file: UploadFile = File(...),
    storage: BodhiStorage = Depends(get_storage),
    cache: BodhiCache | None = Depends(get_cache),
):
    """Upload a PDF, DOCX, or TXT file. Extracts text, ingests into RAG,
    and caches suggested interview topics in Redis."""
    from src.document_parser import extract_text_from_file

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(400, "Empty file")

    try:
        text = extract_text_from_file(file_bytes, file.filename or "upload.txt")
    except ValueError as e:
        raise HTTPException(400, str(e))

    if not text.strip():
        raise HTTPException(400, "No text could be extracted from the file")

    n = ingest_document(
        company=company,
        role=role,
        text=text,
        storage=storage,
        source_label=file.filename or "upload",
    )

    topics: list[str] = []
    try:
        topics = extract_topics(text, company, role)
        if topics and cache:
            existing = cache.get_topics(company, role) or []
            merged = list(dict.fromkeys(existing + topics))[:20]
            cache.set_topics(company, role, merged)
    except Exception:
        pass

    return UploadResponse(chunks_ingested=n, topics_extracted=topics)


@router.get("/search", response_model=list[SearchResult])
async def search_documents(
    company: str,
    role: str = "general",
    query: str = "",
    top_k: int = 5,
    storage: BodhiStorage = Depends(get_storage),
):
    from src.embeddings import get_embedding

    if not query:
        query = f"{company} {role} interview preparation"
    emb = get_embedding(query)
    results = storage.search_similar_chunks(company, role, emb, top_k=top_k)
    return [SearchResult(**r) for r in results]


@router.get("/context", response_model=ContextResponse)
async def get_context(
    company: str,
    role: str = "general",
    storage: BodhiStorage = Depends(get_storage),
    cache: BodhiCache | None = Depends(get_cache),
):
    if cache:
        cached = cache.get_rag_context(company, role)
        if cached:
            return ContextResponse(company=company, role=role, context=cached)

    ctx = retrieve_context(company, role, storage)
    if cache and ctx:
        cache.set_rag_context(company, role, ctx)
    return ContextResponse(company=company, role=role, context=ctx)


@router.get("/topics", response_model=TopicsResponse)
async def get_topics(
    company: str,
    role: str = "general",
    cache: BodhiCache | None = Depends(get_cache),
):
    topics: list[str] = []
    if cache:
        topics = cache.get_topics(company, role) or []
    return TopicsResponse(company=company, role=role, topics=topics)
