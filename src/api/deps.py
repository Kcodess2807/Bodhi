"""FastAPI dependency injection helpers.

All shared resources (storage, cache, LLM, graph) live on app.state
and are injected into endpoint functions via Depends().
"""

from __future__ import annotations

from fastapi import Depends, Request

from src.cache import BodhiCache
from src.storage import BodhiStorage
from src.api.auth import require_auth, get_current_user_id  # noqa: F401


def get_storage(request: Request) -> BodhiStorage:
    return request.app.state.storage


def get_cache(request: Request) -> BodhiCache | None:
    return request.app.state.cache


def get_graph(request: Request):
    return request.app.state.graph


def get_sarvam_key(request: Request) -> str:
    return request.app.state.sarvam_key



def get_llm(request: Request):
    return request.app.state.llm
