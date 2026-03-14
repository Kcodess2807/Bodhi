"""FastAPI application — entry point for the Bodhi HTTP server."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

# Configure logging for Bodhi debug output
import logging
logging.basicConfig(level=logging.INFO)
logging.getLogger("bodhi").setLevel(logging.DEBUG)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from src.storage import BodhiStorage
    from src.cache import BodhiCache
    from src.services.llm import create_llm
    from src.graph import build_interview_graph

    db_url = os.getenv("DATABASE_URL", "")
    if not db_url:
        raise RuntimeError("DATABASE_URL is required for the API server")

    storage = BodhiStorage(db_url)
    storage.init_tables()
    app.state.storage = storage

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    try:
        cache = BodhiCache(redis_url)
        if not cache.ping():
            cache = None
    except Exception:
        cache = None
    app.state.cache = cache

    google_key = os.getenv("GOOGLE_API_KEY", "")
    llm = create_llm(api_key=google_key, model="gemini-3.1-flash-lite-preview")
    app.state.llm = llm
    app.state.graph = build_interview_graph(llm)
    app.state.sarvam_key = os.getenv("SARVAM_API_KEY", "")

    yield

    storage.close()


app = FastAPI(
    title="Bodhi API",
    description="Voice-first AI Mock Interviewer — HTTP API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-Bodhi-Text",
        "X-Bodhi-Phase",
        "X-Bodhi-End",
        "X-Bodhi-Session",
        "X-Bodhi-Transcript",
    ],
)

from src.api.roles import router as roles_router
from src.api.companies import router as companies_router
from src.api.documents import router as documents_router
from src.api.interviews import router as interviews_router
from src.api.audio import router as audio_router

app.include_router(roles_router)
app.include_router(companies_router)
app.include_router(documents_router)
app.include_router(interviews_router)
app.include_router(audio_router)


@app.get("/health")
@app.get("/api/health")
async def health():
    return {"status": "ok"}
