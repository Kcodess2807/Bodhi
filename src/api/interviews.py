"""Interview session lifecycle endpoints."""

from __future__ import annotations

import base64
import os
import uuid
import urllib.parse

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from langchain_core.messages import HumanMessage

from src.api.deps import get_cache, get_graph, get_llm, get_sarvam_key, get_storage, require_auth
from src.api.models import (
    InterviewStartRequest,
    InterviewStartResponse,
    MessageRequest,
    MessageResponse,
    SessionEndResponse,
    SessionStateResponse,
)
from src.cache import BodhiCache
from src.services.llm import _extract_text
from src.storage import BodhiStorage

router = APIRouter(prefix="/api/interviews", tags=["interviews"])


def _load_entity_context(company: str, role: str, cache, storage) -> str:
    """Load company context + role profile, merging RAG and role data."""
    ctx_parts: list[str] = []

    # --- Role profile (independent of company) ---
    if storage and role:
        try:
            role_profile = storage.get_role(role)
            if role_profile:
                if role_profile.get("focus_areas"):
                    ctx_parts.append(f"Role focus areas: {role_profile['focus_areas']}")
                if role_profile.get("typical_topics"):
                    ctx_parts.append(f"Typical interview topics: {role_profile['typical_topics']}")
                if role_profile.get("description"):
                    ctx_parts.append(f"Role description: {role_profile['description']}")
        except Exception:
            pass

    # --- Company / RAG context ---
    if company:
        rag_ctx = ""
        if cache:
            cached = cache.get_rag_context(company, role)
            if cached:
                rag_ctx = cached

        if not rag_ctx and storage:
            try:
                from src.rag import retrieve_context
                rag_ctx = retrieve_context(company, role, storage) or ""
                if rag_ctx and cache:
                    cache.set_rag_context(company, role, rag_ctx)
            except Exception:
                pass

        if not rag_ctx and storage:
            entity = storage.get_entity(company)
            if entity:
                rag_ctx = (
                    f"{entity.get('description', '')} "
                    f"Hiring: {entity.get('hiring_patterns', '')} "
                    f"Tech: {entity.get('tech_stack', '')}"
                ).strip()
                if rag_ctx and cache:
                    cache.set_rag_context(company, role, rag_ctx)

        if rag_ctx:
            ctx_parts.append(rag_ctx)

    return "\n".join(ctx_parts)


def _load_candidate_context(
    mode: str,
    user_id: str | None,
    jd_text: str | None,
    storage,
    llm,
) -> tuple[dict, str, dict]:
    """Return (candidate_profile, jd_context, gap_map) for resume-based modes.

    For standard mode returns empty defaults. Raises HTTPException on missing inputs.
    """
    # normalise frontend aliases
    if mode == "mode_a":
        mode = "option_a"
    elif mode == "mode_b":
        mode = "option_b"

    if mode == "standard":
        return {}, "", {}

    if not user_id:
        raise HTTPException(400, f"user_id is required for mode '{mode}'")

    row = storage.get_user_profile(user_id)
    if not row:
        raise HTTPException(404, f"No profile found for user_id '{user_id}'")

    profile = row["professional_summary"]

    if mode == "option_a":
        return profile, "", {}

    # option_b — needs JD
    if not jd_text or not jd_text.strip():
        raise HTTPException(400, "jd_text is required for mode 'option_b'")

    gap_map: dict = {}
    if llm:
        try:
            from src.resume_parser import build_gap_map
            gap_map = build_gap_map(profile, jd_text, llm)
        except Exception:
            gap_map = {}

    return profile, jd_text, gap_map


def _load_suggested_topics(company: str, role: str, cache) -> str:
    if not cache:
        return ""
    topics = cache.get_topics(company, role)
    if not topics:
        return ""
    return "\n".join(f"  - {t}" for t in topics)


_CURRICULUM_PROMPT = """\
You are an expert technical interviewer preparing a custom interview curriculum.
Generate exactly 2 targeted questions for each of the following 2 phases for a {role} at {company}.
Use the provided company profile and job description to make the questions highly specific and realistic.

COMPANY PROFILE:
{profile_text}

{jd_block}

OUTPUT FORMAT:
Return a valid JSON object with EXACTLY two keys: "technical" and "dsa".
"technical": 2 domain-relevant technical questions (e.g. language internals, framework concepts, system design).
"dsa": 2 data structures & algorithms questions (e.g. array/tree/graph problems with clear input/output).
Each key must contain a list of exactly 2 question strings.
DO NOT include any markdown blocks (like ```json), just raw JSON.
"""

def generate_interview_curriculum(company: str, role: str, storage: BodhiStorage, jd_text: str = "") -> dict:
    """Generate 2 technical + 2 DSA pre-decided questions based on company profile and JD."""
    from src.services.llm import create_llm, _extract_text
    from langchain_core.messages import HumanMessage
    import json
    import logging
    log = logging.getLogger("bodhi.curriculum")
    
    profile_parts = []
    try:
        if storage:
            entity = storage.get_entity(company)
            if entity:
                profile_parts.append(f"Company Description: {entity.get('description', '')}")
                profile_parts.append(f"Company Tech Stack: {entity.get('tech_stack', '')}")
                profile_parts.append(f"Company Hiring Patterns: {entity.get('hiring_patterns', '')}")
                
            profiles = storage.get_company_profiles(company)
            for p in profiles:
                if p.get("role", "").lower() == role.lower():
                    profile_parts.append(f"Role Specific Description: {p.get('description', '')}")
                    profile_parts.append(f"Role Tech Stack: {p.get('tech_stack', '')}")
                    profile_parts.append(f"Role Hiring Patterns: {p.get('hiring_patterns', '')}")
                    break
    except Exception as e:
        log.error(f"Failed to fetch profile from DB: {e}")
        
    profile_text = "\n".join(filter(None, profile_parts))
    if not profile_text.strip():
        profile_text = "No specific company data available. Generate standard questions."
    
    jd_block = ""
    if jd_text and jd_text.strip():
        jd_block = f"JOB DESCRIPTION (provided by candidate):\n{jd_text[:8000]}"
        log.info(f"[CURRICULUM] JD text provided ({len(jd_text)} chars)")
    
    llm = create_llm(api_key=os.getenv("GOOGLE_API_KEY", ""))
    prompt = _CURRICULUM_PROMPT.format(
        role=role, company=company, profile_text=profile_text, jd_block=jd_block
    )
    
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        raw = _extract_text(response.content).strip()
        if raw.startswith("```json"): raw = raw[7:]
        if raw.startswith("```"): raw = raw[3:]
        if raw.endswith("```"): raw = raw[:-3]
        
        data = json.loads(raw.strip())
        
        result = {
            "technical": data.get("technical", [])[:2],
            "dsa": data.get("dsa", [])[:2],
        }
        
        # DEBUG output
        log.info("==================================================")
        log.info(f"PRE-GENERATED CURRICULUM FOR {company} | {role}")
        log.info(f"  Technical ({len(result['technical'])} Qs): {result['technical']}")
        log.info(f"  DSA ({len(result['dsa'])} Qs): {result['dsa']}")
        if jd_text:
            log.info(f"  JD context: YES ({len(jd_text)} chars)")
        log.info("==================================================")
        
        return result
    except Exception as e:
        log.error(f"Curriculum generation failed: {e}")
        return {"technical": [], "dsa": []}


@router.post("", response_model=InterviewStartResponse, status_code=201)
async def start_interview(
    body: InterviewStartRequest,
    user_id: str = Depends(require_auth),
    graph=Depends(get_graph),
    storage: BodhiStorage = Depends(get_storage),
    cache: BodhiCache | None = Depends(get_cache),
    sarvam_key: str = Depends(get_sarvam_key),
    llm=Depends(get_llm),
):
    session_id = uuid.uuid4().hex[:12]

    resolved_user_profile_id = body.user_id
    if not resolved_user_profile_id and storage:
        resolved_user_profile_id = storage.get_user_profile_id_by_clerk_user_id(user_id)

    candidate_profile, jd_context, gap_map = _load_candidate_context(
        body.mode, resolved_user_profile_id, body.jd_text, storage, llm
    )
    entity_context = _load_entity_context(body.company, body.role, cache, storage)
    suggested_topics = _load_suggested_topics(body.company, body.role, cache)
    
    # Pre-generate curriculum (2 technical + 2 DSA questions)
    curriculum = generate_interview_curriculum(body.company, body.role, storage, jd_text=body.jd_text)
    if cache:
        for phase, questions in curriculum.items():
            cache.set_question_queue(session_id, phase, questions)

    try:
        storage.create_session(
            session_id,
            body.candidate_name,
            body.company,
            body.role,
            clerk_user_id=user_id,
            user_profile_id=resolved_user_profile_id,
        )
    except Exception:
        pass

    graph_config = {"configurable": {"thread_id": session_id}}
    initial_state = {
        "messages": [HumanMessage(content="Hello, I'm ready for my interview.")],
        "session_id": session_id,
        "candidate_name": body.candidate_name,
        "target_company": body.company,
        "target_role": body.role,
        "current_phase": "intro",
        "difficulty_level": 3,
        "phase_scores": {},
        "entity_context": entity_context,
        "suggested_topics": suggested_topics,
        "should_end": False,
        "queued_questions": curriculum,
        "target_question": "",  # intro is ad-hoc, no target question
        "interview_mode": body.mode,
        "candidate_profile": candidate_profile,
        "jd_context": jd_context,
        "gap_map": gap_map,
    }

    result = graph.invoke(initial_state, config=graph_config)
    greeting = _extract_text(
        result["messages"][-1].content
        if result["messages"] and hasattr(result["messages"][-1], "content")
        else ""
    )

    audio_b64 = ""
    if sarvam_key and greeting:
        try:
            from src.services.tts import text_to_speech_bytes
            audio_bytes = text_to_speech_bytes(
                greeting, api_key=sarvam_key, target_language_code="hi-IN", speaker="shubh",
            )
            audio_b64 = base64.b64encode(audio_bytes).decode()
        except Exception:
            pass

    return InterviewStartResponse(
        session_id=session_id,
        greeting_text=greeting,
        greeting_audio_b64=audio_b64,
    )


@router.post("/{session_id}/message", response_model=MessageResponse)
async def send_message(
    session_id: str,
    body: MessageRequest,
    user_id: str = Depends(require_auth),
    graph=Depends(get_graph),
    cache: BodhiCache | None = Depends(get_cache),
    sarvam_key: str = Depends(get_sarvam_key),
):
    graph_config = {"configurable": {"thread_id": session_id}}

    try:
        state = graph.get_state(graph_config)
        if not state or not state.values:
            raise HTTPException(404, f"Session '{session_id}' not found")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(404, f"Session '{session_id}' not found")

    result = graph.invoke(
        {"messages": [HumanMessage(content=body.text)]},
        config=graph_config,
    )

    reply = ""
    if result["messages"] and hasattr(result["messages"][-1], "content"):
        reply = _extract_text(result["messages"][-1].content).strip()

    phase = result.get("current_phase", "unknown")
    should_end = result.get("should_end", False)

    audio_b64 = ""
    if sarvam_key and reply:
        try:
            from src.services.tts import text_to_speech_bytes
            audio_bytes = text_to_speech_bytes(
                reply, api_key=sarvam_key, target_language_code="hi-IN", speaker="shubh",
            )
            audio_b64 = base64.b64encode(audio_bytes).decode()
        except Exception:
            pass

    if cache:
        try:
            cache.save_session_state(session_id, {
                "phase": phase,
                "difficulty": result.get("difficulty_level", 3),
                "scores": result.get("phase_scores", {}),
            })
        except Exception:
            pass

    if should_end:
        _flush_session_async(session_id, result, graph_config)

    return MessageResponse(
        transcript=body.text,
        reply_text=reply,
        reply_audio_b64=audio_b64,
        phase=phase,
        should_end=should_end,
    )


@router.post("/{session_id}/audio", response_model=MessageResponse)
async def send_audio(
    session_id: str,
    file: UploadFile = File(...),
    user_id: str = Depends(require_auth),
    graph=Depends(get_graph),
    storage: BodhiStorage = Depends(get_storage),
    cache: BodhiCache | None = Depends(get_cache),
    sarvam_key: str = Depends(get_sarvam_key),
):
    """Upload WAV audio, transcribe via STT, then process through interview graph."""
    graph_config = {"configurable": {"thread_id": session_id}}

    try:
        state = graph.get_state(graph_config)
        if not state or not state.values:
            raise HTTPException(404, f"Session '{session_id}' not found")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(404, f"Session '{session_id}' not found")

    audio_bytes = await file.read()
    if not audio_bytes or len(audio_bytes) < 1000:
        raise HTTPException(400, "Audio file too small or empty")

    if not sarvam_key:
        raise HTTPException(500, "SARVAM_API_KEY not configured")

    from src.services.stt import transcribe_audio
    transcript = transcribe_audio(
        audio_bytes, api_key=sarvam_key, model="saaras:v3", language_code="en-IN",
    )

    transcript = (transcript or "").strip()
    if not transcript:
        raise HTTPException(422, "Could not transcribe audio")

    result = graph.invoke(
        {"messages": [HumanMessage(content=transcript)]},
        config=graph_config,
    )

    reply = ""
    if result["messages"] and hasattr(result["messages"][-1], "content"):
        reply = _extract_text(result["messages"][-1].content).strip()

    phase = result.get("current_phase", "unknown")
    should_end = result.get("should_end", False)

    audio_b64 = ""
    if sarvam_key and reply:
        try:
            from src.services.tts import text_to_speech_bytes
            audio_bytes_out = text_to_speech_bytes(
                reply, api_key=sarvam_key, target_language_code="hi-IN", speaker="shubh",
            )
            audio_b64 = base64.b64encode(audio_bytes_out).decode()
        except Exception:
            pass

    if cache:
        try:
            cache.save_session_state(session_id, {
                "phase": phase,
                "difficulty": result.get("difficulty_level", 3),
                "scores": result.get("phase_scores", {}),
            })
        except Exception:
            pass

    if should_end:
        _flush_session_async(session_id, result, graph_config)

    return MessageResponse(
        transcript=transcript,
        reply_text=reply,
        reply_audio_b64=audio_b64,
        phase=phase,
        should_end=should_end,
    )


@router.get("/{session_id}", response_model=SessionStateResponse)
async def get_session(
    session_id: str,
    user_id: str = Depends(require_auth),
    graph=Depends(get_graph),
):
    graph_config = {"configurable": {"thread_id": session_id}}
    try:
        state = graph.get_state(graph_config)
        if not state or not state.values:
            raise HTTPException(404, f"Session '{session_id}' not found")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(404, f"Session '{session_id}' not found")

    vals = state.values
    return SessionStateResponse(
        session_id=vals.get("session_id", session_id),
        phase=vals.get("current_phase", "unknown"),
        difficulty_level=vals.get("difficulty_level", 3),
        phase_scores=vals.get("phase_scores", {}),
        company=vals.get("target_company", ""),
        role=vals.get("target_role", ""),
    )


@router.post("/{session_id}/end", response_model=SessionEndResponse)
async def end_interview(
    session_id: str,
    user_id: str = Depends(require_auth),
    graph=Depends(get_graph),
    storage: BodhiStorage = Depends(get_storage),
    cache: BodhiCache | None = Depends(get_cache),
):
    graph_config = {"configurable": {"thread_id": session_id}}
    try:
        state = graph.get_state(graph_config)
        if not state or not state.values:
            raise HTTPException(404, f"Session '{session_id}' not found")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(404, f"Session '{session_id}' not found")

    vals = state.values
    summary, overall_score = _flush_session_sync(session_id, vals, storage, cache)

    return SessionEndResponse(
        session_id=session_id,
        summary=summary,
        overall_score=overall_score,
    )


def _flush_session_async(session_id: str, result: dict, graph_config: dict):
    """Best-effort session flush (non-blocking in the response path)."""
    pass


def _flush_session_sync(
    session_id: str,
    state: dict,
    storage: BodhiStorage,
    cache: BodhiCache | None,
) -> tuple[str, float | None]:
    """Flush session data to NeonDB, trigger RAG contribution, clean up Redis.
    Returns (summary, overall_score)."""
    transcript_text = ""
    summary = ""
    overall_score: float | None = None

    try:
        messages = []
        for msg in state.get("messages", []):
            role = "user" if isinstance(msg, HumanMessage) else "assistant"
            content = msg.content if hasattr(msg, "content") else str(msg)
            messages.append({"role": role, "content": _extract_text(content)})

        transcript_text = "\n".join(
            f"{m['role']}: {m['content']}" for m in messages
        )

        storage.save_transcript_batch(
            session_id, messages, state.get("current_phase", "unknown"),
        )

        scores = state.get("phase_scores", {})
        total_score = 0.0
        total_q = 0
        for phase, data in scores.items():
            q = data.get("questions", 0)
            s = data.get("total_score", 0)
            storage.save_phase_result(
                session_id,
                phase,
                score=s / q if q else 0,
                question_count=q,
                difficulty_reached=state.get("difficulty_level", 3),
                feedback=data.get("feedback", []),
            )
            total_score += s
            total_q += q

        overall_score = total_score / total_q if total_q else None
        summary = f"Interview complete. {total_q} questions across {len(scores)} phases."
        storage.end_session(session_id, overall_score=overall_score, summary=summary)
    except Exception:
        pass

    if transcript_text:
        try:
            from src.rag import extract_and_contribute
            company = state.get("target_company", "")
            role = state.get("target_role", "")
            extract_and_contribute(company, role, transcript_text, storage)
        except Exception:
            pass

    if cache:
        try:
            cache.delete_session(session_id)
        except Exception:
            pass

    return summary, overall_score


# ── Streaming endpoints ───────────────────────────────────────────

import json as _json
import re
import asyncio
import logging
from typing import Optional

from src.services.sentiment import analyze_tone as _analyze_tone

_stream_log = logging.getLogger("bodhi.api.stream")


async def _tts_stream_generator(text: str, sarvam_key: str):
    """Yield MP3 audio chunks from TTS streaming (legacy full-text mode)."""
    _stream_log.info("Starting TTS stream for %d chars of text", len(text))
    from src.services.tts import text_to_speech_stream
    chunk_count = 0
    try:
        async for chunk in text_to_speech_stream(
            text, api_key=sarvam_key, target_language_code="hi-IN", speaker="shubh",
        ):
            chunk_count += 1
            _stream_log.debug("Yielding chunk #%d (%d bytes)", chunk_count, len(chunk))
            yield chunk
    except Exception as exc:
        _stream_log.error("TTS stream generator error: %s: %s", type(exc).__name__, exc, exc_info=True)
        raise
    _stream_log.info("TTS stream generator done: %d chunks yielded", chunk_count)


_SENTENCE_END = re.compile(r'(?<=[.!?])\s')


async def _sentence_accumulator(token_aiter):
    """Consume an async iterator of LLM tokens and yield complete sentences.

    Splits on sentence boundaries (.!?) so TTS gets coherent phrases.
    Flushes any remaining buffer at the end.
    """
    buf = ""
    async for token in token_aiter:
        buf += token
        # Check for sentence boundaries
        parts = _SENTENCE_END.split(buf)
        if len(parts) > 1:
            # All but last part are complete sentences
            for sentence in parts[:-1]:
                sentence = sentence.strip()
                if sentence:
                    _stream_log.info("[ACCUMULATOR] Yielding sentence: %s", sentence[:80])
                    yield sentence
            buf = parts[-1]
    # Flush remainder
    buf = buf.strip()
    if buf:
        _stream_log.info("[ACCUMULATOR] Yielding final fragment: %s", buf[:80])
        yield buf


async def _llm_tts_pipeline(graph, graph_config, user_input, sarvam_key: str):
    """Pipeline: LLM tokens → sentence accumulator → TTS audio chunks.

    Uses graph.astream_events() to get individual LLM tokens, accumulates
    them into sentences, and feeds sentences to TTS concurrently.

    Yields:
        (audio_chunk: bytes | None, meta: dict | None)
        - audio chunks as they arrive
        - a final meta dict with {reply_text, phase, should_end} after all audio

    The meta dict is yielded LAST with audio_chunk=None so the caller can
    extract state info for cache/headers.
    """
    from src.services.tts import tts_stream_sentences

    collected_text = []
    phase = "unknown"
    should_end = False

    # Async generator that extracts LLM tokens from astream_events
    async def _llm_tokens():
        nonlocal phase, should_end
        try:
            async for event in graph.astream_events(
                {"messages": [HumanMessage(content=user_input)]},
                config=graph_config,
                version="v2",
            ):
                kind = event.get("event", "")

                if kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content"):
                        token_text = _extract_text(chunk.content)
                        if token_text:
                            collected_text.append(token_text)
                            yield token_text

                elif kind == "on_tool_end":
                    output = event.get("data", {}).get("output", "")
                    if hasattr(output, "content"):
                        output = output.content
                    output = str(output)
                    if output.startswith("TRANSITION:"):
                        phase = output.split(":", 1)[1]
                        _stream_log.info("[PIPELINE] Phase transition → %s", phase)
                    elif output.startswith("END:"):
                        should_end = True
                        _stream_log.info("[PIPELINE] Interview end triggered")

        except Exception as e:
            _stream_log.error("[PIPELINE] astream_events error: %s", e, exc_info=True)

    # Pipeline: LLM tokens → sentences → TTS audio
    sentence_stream = _sentence_accumulator(_llm_tokens())

    chunk_count = 0
    try:
        async for audio_chunk in tts_stream_sentences(
            sentence_stream,
            api_key=sarvam_key,
            target_language_code="hi-IN",
            speaker="shubh",
        ):
            chunk_count += 1
            yield audio_chunk, None
    except Exception as exc:
        _stream_log.error("[PIPELINE] TTS pipeline error: %s", exc, exc_info=True)

    # After all audio, get the current state for headers/cache
    try:
        state = graph.get_state(graph_config)
        if state and state.values:
            phase = state.values.get("current_phase", phase)
            should_end = state.values.get("should_end", should_end)
    except Exception:
        pass

    reply_text = "".join(collected_text).strip()
    _stream_log.info("[PIPELINE] Done: %d audio chunks, %d chars reply, phase=%s, end=%s",
                     chunk_count, len(reply_text), phase, should_end)

    yield None, {"reply_text": reply_text, "phase": phase, "should_end": should_end}


async def _pipeline_audio_generator(graph, graph_config, user_input, sarvam_key, result_holder: dict):
    """Async generator that yields only audio bytes from the pipeline.
    Stores the final metadata in result_holder for the caller to inspect."""
    async for audio_chunk, meta in _llm_tts_pipeline(graph, graph_config, user_input, sarvam_key):
        if audio_chunk is not None:
            yield audio_chunk
        elif meta is not None:
            result_holder.update(meta)


def _stream_headers(**kwargs: str) -> dict[str, str]:
    """Build custom response headers for streaming endpoints.
    Values are URL-encoded to safely transport arbitrary text in HTTP headers."""
    headers = {}
    for key, val in kwargs.items():
        if val is not None:
            headers[f"X-Bodhi-{key}"] = urllib.parse.quote(str(val), safe="")
    return headers


@router.post("/start-stream")
async def start_interview_stream(
    body: InterviewStartRequest,
    user_id: str = Depends(require_auth),
    graph=Depends(get_graph),
    storage: BodhiStorage = Depends(get_storage),
    cache: BodhiCache | None = Depends(get_cache),
    sarvam_key: str = Depends(get_sarvam_key),
    llm=Depends(get_llm),
):
    """Start interview and stream greeting audio as MP3.
    Metadata is returned in response headers."""
    import json
    loop = asyncio.get_event_loop()
    session_id = uuid.uuid4().hex[:12]

    resolved_user_profile_id = body.user_id
    if not resolved_user_profile_id and storage:
        resolved_user_profile_id = storage.get_user_profile_id_by_clerk_user_id(user_id)

    _stream_log.info("[START-STREAM] Session %s: loading context...", session_id)

    # Run all blocking I/O in thread pool to avoid blocking event loop
    candidate_profile, jd_context, gap_map = await loop.run_in_executor(
        None, lambda: _load_candidate_context(body.mode, resolved_user_profile_id, body.jd_text, storage, llm)
    )
    entity_context = await loop.run_in_executor(
        None, lambda: _load_entity_context(body.company, body.role, cache, storage)
    )
    suggested_topics = await loop.run_in_executor(
        None, lambda: _load_suggested_topics(body.company, body.role, cache)
    )

    # Pre-generate curriculum (2 technical + 2 DSA questions)
    _stream_log.info("[START-STREAM] Session %s: generating curriculum...", session_id)
    curriculum = await loop.run_in_executor(
        None, lambda: generate_interview_curriculum(body.company, body.role, storage, jd_text=body.jd_text)
    )
    if cache:
        for phase, questions in curriculum.items():
            cache.set_question_queue(session_id, phase, questions)

    try:
        await loop.run_in_executor(
            None,
            lambda: storage.create_session(
                session_id,
                body.candidate_name,
                body.company,
                body.role,
                clerk_user_id=user_id,
                user_profile_id=resolved_user_profile_id,
            ),
        )
    except Exception:
        pass

    graph_config = {"configurable": {"thread_id": session_id}}
    initial_state = {
        "messages": [HumanMessage(content="Hello, I'm ready for my interview.")],
        "session_id": session_id,
        "candidate_name": body.candidate_name,
        "target_company": body.company,
        "target_role": body.role,
        "current_phase": "intro",
        "difficulty_level": 3,
        "phase_scores": {},
        "entity_context": entity_context,
        "suggested_topics": suggested_topics,
        "should_end": False,
        "queued_questions": curriculum,
        "target_question": "",  # intro is ad-hoc, no target question
        "interview_mode": body.mode,
        "candidate_profile": candidate_profile,
        "jd_context": jd_context,
        "gap_map": gap_map,
    }

    _stream_log.info("[START-STREAM] Session %s: invoking graph for greeting...", session_id)
    result = await loop.run_in_executor(
        None, lambda: graph.invoke(initial_state, config=graph_config)
    )
    greeting = _extract_text(
        result["messages"][-1].content
        if result["messages"] and hasattr(result["messages"][-1], "content")
        else ""
    )
    _stream_log.info("[START-STREAM] Session %s: greeting ready (%d chars)", session_id, len(greeting))

    if not sarvam_key or not greeting:
        raise HTTPException(500, "TTS not available")

    # Serialize curriculum for frontend debugging
    curriculum_json = json.dumps(curriculum) if curriculum else "{}"

    headers = _stream_headers(
        Session=session_id,
        Text=greeting,
        Phase="intro",
        End="false",
        Curriculum=curriculum_json,
    )

    return StreamingResponse(
        _tts_stream_generator(greeting, sarvam_key),
        media_type="audio/mpeg",
        headers=headers,
    )


@router.post("/{session_id}/message-stream")
async def send_message_stream(
    session_id: str,
    body: MessageRequest,
    user_id: str = Depends(require_auth),
    graph=Depends(get_graph),
    cache: BodhiCache | None = Depends(get_cache),
    sarvam_key: str = Depends(get_sarvam_key),
):
    """Send text message and stream reply audio as MP3 (low-latency pipeline)."""
    graph_config = {"configurable": {"thread_id": session_id}}

    try:
        state = graph.get_state(graph_config)
        if not state or not state.values:
            raise HTTPException(404, f"Session '{session_id}' not found")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(404, f"Session '{session_id}' not found")

    if not sarvam_key:
        raise HTTPException(500, "SARVAM_API_KEY not configured")

    result_holder: dict = {}

    async def _gen():
        async for chunk in _pipeline_audio_generator(
            graph, graph_config, body.text, sarvam_key, result_holder
        ):
            yield chunk
        # Post-stream: cache update
        if cache:
            try:
                st = graph.get_state(graph_config)
                if st and st.values:
                    cache.save_session_state(session_id, {
                        "phase": st.values.get("current_phase", "unknown"),
                        "difficulty": st.values.get("difficulty_level", 3),
                        "scores": st.values.get("phase_scores", {}),
                    })
            except Exception:
                pass
        if result_holder.get("should_end"):
            _flush_session_async(session_id, {}, graph_config)

    headers = _stream_headers(
        Transcript=body.text,
        Phase="streaming",
        End="false",
    )

    return StreamingResponse(
        _gen(),
        media_type="audio/mpeg",
        headers=headers,
    )


@router.post("/{session_id}/audio-stream")
async def send_audio_stream(
    session_id: str,
    file: UploadFile = File(...),
    image_file: Optional[UploadFile] = File(None),
    user_id: str = Depends(require_auth),
    graph=Depends(get_graph),
    storage: BodhiStorage = Depends(get_storage),
    cache: BodhiCache | None = Depends(get_cache),
    sarvam_key: str = Depends(get_sarvam_key),
):
    """Upload WAV audio (+ optional webcam frame) and stream reply audio as MP3."""
    graph_config = {"configurable": {"thread_id": session_id}}

    try:
        state = graph.get_state(graph_config)
        if not state or not state.values:
            raise HTTPException(404, f"Session '{session_id}' not found")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(404, f"Session '{session_id}' not found")

    audio_bytes = await file.read()
    if not audio_bytes or len(audio_bytes) < 1000:
        raise HTTPException(400, "Audio file too small or empty")

    image_bytes = (await image_file.read()) if image_file else None

    if not sarvam_key:
        raise HTTPException(500, "SARVAM_API_KEY not configured")

    from src.services.stt import transcribe_audio
    transcript = transcribe_audio(
        audio_bytes, api_key=sarvam_key, model="saaras:v3", language_code="en-IN",
    )

    transcript = (transcript or "").strip()
    if not transcript:
        raise HTTPException(422, "Could not transcribe audio")

    # ── Sentiment analysis ────────────────────────────────────────────────────
    loop = asyncio.get_running_loop()
    sentiment_payload: dict = {}

    try:
        # Rule-based (~1ms, always runs)
        rb = _analyze_tone(transcript, audio_bytes)
        sentiment_payload = rb.to_dict()

        # HuggingFace speech emotion in thread pool (~300ms)
        async def _hf_analysis():
            try:
                from behavioral_analysis.services.speech_service import analyze_speech
                return await loop.run_in_executor(
                    None, lambda: analyze_speech(audio_bytes, file.filename or "audio.wav")
                )
            except Exception as e:
                _stream_log.warning("HF speech analysis failed: %s", e)
                return {}

        # MediaPipe posture in thread pool (~100ms, only when frame sent)
        async def _posture_analysis():
            if not image_bytes:
                return {}
            try:
                from behavioral_analysis.services.posture_service import analyze_posture
                return await loop.run_in_executor(None, lambda: analyze_posture(image_bytes))
            except Exception as e:
                _stream_log.warning("Posture analysis failed: %s", e)
                return {}

        hf_result, posture_result = await asyncio.gather(_hf_analysis(), _posture_analysis())

        if hf_result:
            sentiment_payload.update({
                "hf_emotion":       hf_result.get("emotion"),
                "hf_confidence":    hf_result.get("emotion_confidence"),
                "sentiment":        hf_result.get("sentiment"),
                "pitch_variance":   hf_result.get("pitch_variance"),
                "confidence_score": hf_result.get("confidence_score"),
                "flags":            hf_result.get("flags", []),
            })
        if posture_result:
            sentiment_payload.update({
                "posture":         posture_result.get("posture"),
                "head_tilt_angle": posture_result.get("head_tilt_angle"),
                "gaze_direction":  posture_result.get("gaze_direction"),
                "spine_score":     posture_result.get("spine_score"),
                "face_visible":    posture_result.get("face_visible"),
                "posture_flags":   posture_result.get("flags", []),
            })
    except Exception as e:
        _stream_log.error("Sentiment block failed: %s", e)

    # ── Build streaming response ──────────────────────────────────────────────

    result_holder: dict = {}

    async def _gen():
        async for chunk in _pipeline_audio_generator(
            graph, graph_config, transcript, sarvam_key, result_holder
        ):
            yield chunk
        if cache:
            try:
                st = graph.get_state(graph_config)
                if st and st.values:
                    cache.save_session_state(session_id, {
                        "phase": st.values.get("current_phase", "unknown"),
                        "difficulty": st.values.get("difficulty_level", 3),
                        "scores": st.values.get("phase_scores", {}),
                    })
            except Exception:
                pass
        if result_holder.get("should_end"):
            _flush_session_async(session_id, {}, graph_config)

    headers = _stream_headers(
        Transcript=transcript,
        Phase="streaming",
        End="false",
        Sentiment=_json.dumps(sentiment_payload),
    )

    return StreamingResponse(
        _gen(),
        media_type="audio/mpeg",
        headers=headers,
    )
