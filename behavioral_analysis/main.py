"""Behavioral Analysis API — standalone FastAPI application.

Run with:
    uvicorn behavioral_analysis.main:app --reload --port 8001

Or from the project root:
    python -m uvicorn behavioral_analysis.main:app --reload --port 8001
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from behavioral_analysis.routers.test_analysis import router as test_router
from behavioral_analysis.services import posture_service, speech_service

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-load all models at startup so the first request isn't slow."""
    print("[Bodhi Behavioral] Loading HuggingFace emotion + sentiment models...")
    speech_service.load_models()
    print("[Bodhi Behavioral] Loading MediaPipe Pose + FaceMesh models...")
    posture_service.load_models()
    print("[Bodhi Behavioral] All models ready.")
    yield
    # Nothing to teardown — MediaPipe and HF pipelines are stateless


app = FastAPI(
    title="Bodhi Behavioral Analysis API",
    description=(
        "Test endpoint for the speech sentiment + posture analysis pipeline. "
        "No database, no WebSocket, no face verification — pure REST."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(test_router)


@app.get("/", include_in_schema=False)
def root():
    return {
        "service": "Bodhi Behavioral Analysis",
        "docs": "/docs",
        "health": "/api/test/health",
        "analyze": "/api/test/behavioral-analysis",
    }
