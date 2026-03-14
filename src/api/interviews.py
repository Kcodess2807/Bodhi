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

    candidate_profile, jd_context, gap_map = _load_candidate_context(
        body.mode, body.user_id, body.jd_text, storage, llm
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
            session_id, body.candidate_name, body.company, body.role, clerk_user_id=user_id
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


async def _tts_stream_generator(text: str, sarvam_key: str):
    """Yield MP3 audio chunks from TTS streaming."""
    import logging
    log = logging.getLogger("bodhi.api.stream")

    log.info("Starting TTS stream for %d chars of text", len(text))
    from src.services.tts import text_to_speech_stream
    chunk_count = 0
    try:
        async for chunk in text_to_speech_stream(
            text, api_key=sarvam_key, target_language_code="hi-IN", speaker="shubh",
        ):
            chunk_count += 1
            log.debug("Yielding chunk #%d (%d bytes)", chunk_count, len(chunk))
            yield chunk
    except Exception as exc:
        log.error("TTS stream generator error: %s: %s", type(exc).__name__, exc, exc_info=True)
        raise
    log.info("TTS stream generator done: %d chunks yielded", chunk_count)


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
    session_id = uuid.uuid4().hex[:12]

    candidate_profile, jd_context, gap_map = _load_candidate_context(
        body.mode, body.user_id, body.jd_text, storage, llm
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
            session_id, body.candidate_name, body.company, body.role, clerk_user_id=user_id
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

    if not sarvam_key or not greeting:
        raise HTTPException(500, "TTS not available")

    # Serialize curriculum for frontend debugging
    import json
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
    """Send text message and stream reply audio as MP3."""
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

    if not sarvam_key or not reply:
        raise HTTPException(500, "TTS not available or empty reply")

    headers = _stream_headers(
        Text=reply,
        Transcript=body.text,
        Phase=phase,
        End=str(should_end).lower(),
    )

    return StreamingResponse(
        _tts_stream_generator(reply, sarvam_key),
        media_type="audio/mpeg",
        headers=headers,
    )


@router.post("/{session_id}/audio-stream")
async def send_audio_stream(
    session_id: str,
    file: UploadFile = File(...),
    user_id: str = Depends(require_auth),
    graph=Depends(get_graph),
    storage: BodhiStorage = Depends(get_storage),
    cache: BodhiCache | None = Depends(get_cache),
    sarvam_key: str = Depends(get_sarvam_key),
):
    """Upload WAV audio and stream reply audio as MP3."""
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

    if not reply:
        raise HTTPException(500, "Empty reply from interviewer")

    headers = _stream_headers(
        Text=reply,
        Transcript=transcript,
        Phase=phase,
        End=str(should_end).lower(),
    )

    return StreamingResponse(
        _tts_stream_generator(reply, sarvam_key),
        media_type="audio/mpeg",
        headers=headers,
    )
