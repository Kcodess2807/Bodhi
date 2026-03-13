"""Embedding generation using Google text-embedding-004."""

import os

from langchain_google_genai import GoogleGenerativeAIEmbeddings


_model: GoogleGenerativeAIEmbeddings | None = None


def _get_model() -> GoogleGenerativeAIEmbeddings:
    global _model
    if _model is None:
        api_key = os.getenv("GOOGLE_API_KEY", "")
        _model = GoogleGenerativeAIEmbeddings(
            model="models/text-embedding-004",
            google_api_key=api_key,
        )
    return _model


def get_embedding(text: str) -> list[float]:
    """Embed a single text string. Returns a 768-dim float vector."""
    return _get_model().embed_query(text)


def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts. Returns list of 768-dim float vectors."""
    if not texts:
        return []
    return _get_model().embed_documents(texts)
