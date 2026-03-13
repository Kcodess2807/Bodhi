"""RAG system for company profile knowledge base.

Handles document chunking, embedding, ingestion, retrieval, and
post-interview contribution via pgvector on NeonDB.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from src.embeddings import get_embedding, get_embeddings

if TYPE_CHECKING:
    from src.storage import BodhiStorage


def chunk_text(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50,
) -> list[str]:
    """Split text into overlapping word-level chunks."""
    words = text.split()
    if len(words) <= chunk_size:
        return [text.strip()] if text.strip() else []
    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunks.append(" ".join(words[start:end]))
        start = end - overlap
    return chunks


def ingest_document(
    company: str,
    role: str,
    text: str,
    storage: BodhiStorage,
    source_label: str = "",
    contributed_by: str = "",
) -> int:
    """Chunk, embed, and store a document for a company+role.
    Returns the number of chunks inserted."""
    chunks = chunk_text(text)
    if not chunks:
        return 0

    embeddings = get_embeddings(chunks)
    rows = [
        (chunk, idx, emb)
        for idx, (chunk, emb) in enumerate(zip(chunks, embeddings))
    ]
    return storage.insert_document_chunks(
        company, role, rows,
        source_label=source_label,
        contributed_by=contributed_by,
    )


def retrieve_context(
    company: str,
    role: str,
    storage: BodhiStorage,
    query: str | None = None,
    top_k: int = 5,
) -> str:
    """Embed a query and return merged role-only + company-specific context.

    When company is provided, search_similar_chunks already fetches both
    company-specific and role-only general docs (company='general'). When
    company is empty or 'general', only role-level docs are returned.
    """
    effective_company = company if company and company.lower() != "general" else "general"
    if query is None:
        query = f"{effective_company} {role} interview preparation"
    query_emb = get_embedding(query)
    results = storage.search_similar_chunks(effective_company, role, query_emb, top_k=top_k)
    if not results:
        return ""
    return "\n\n".join(r["chunk_text"] for r in results)


_TOPICS_PROMPT = """\
You are an expert interview coach. Given the following document about a {role} position \
{company_clause}, extract 10-15 concrete interview topics or questions that an interviewer \
should explore. Focus on technical skills, domain knowledge, and behavioral competencies \
mentioned in the material.

Output ONLY a numbered list (one topic per line). No preamble, no summary.

DOCUMENT:
{text}
"""


def extract_topics(
    text: str,
    company: str,
    role: str,
) -> list[str]:
    """Use Gemini to extract 10-15 interview topics from document text."""
    if not text or len(text) < 50:
        return []

    from src.services.llm import create_llm, _extract_text
    from langchain_core.messages import HumanMessage

    company_clause = f"at {company}" if company and company.lower() != "general" else "(general)"
    llm = create_llm(api_key=os.getenv("GOOGLE_API_KEY", ""))
    prompt = _TOPICS_PROMPT.format(
        role=role, company_clause=company_clause, text=text[:8000],
    )
    response = llm.invoke([HumanMessage(content=prompt)])
    raw = _extract_text(response.content).strip()

    topics: list[str] = []
    for line in raw.splitlines():
        line = line.strip().lstrip("0123456789.)-] ").strip()
        if line:
            topics.append(line)
    return topics[:15]


_EXTRACT_PROMPT = """\
You are an analyst extracting company-specific intelligence from an interview transcript.

Given the transcript below for a {role} position at {company}, extract ONLY concrete, \
reusable facts about the company's hiring process, technical expectations, culture, \
or interview patterns. Ignore candidate-specific details.

Output a concise paragraph (3-8 sentences). If there is nothing company-specific to \
extract, respond with exactly: NOTHING_TO_EXTRACT

TRANSCRIPT:
{transcript}
"""


def extract_and_contribute(
    company: str,
    role: str,
    transcript: str,
    storage: BodhiStorage,
) -> int:
    """Use Gemini to extract company intel from a transcript, then ingest it.
    Returns number of chunks inserted (0 if nothing extracted)."""
    if not transcript or len(transcript) < 100:
        return 0

    from src.services.llm import create_llm, _extract_text
    from langchain_core.messages import HumanMessage

    llm = create_llm(api_key=os.getenv("GOOGLE_API_KEY", ""))
    prompt = _EXTRACT_PROMPT.format(
        company=company, role=role, transcript=transcript[:8000],
    )
    response = llm.invoke([HumanMessage(content=prompt)])
    extracted = _extract_text(response.content).strip()

    if not extracted or "NOTHING_TO_EXTRACT" in extracted:
        return 0

    return ingest_document(
        company, role, extracted, storage,
        source_label="interview_extract",
        contributed_by="bodhi_auto",
    )
