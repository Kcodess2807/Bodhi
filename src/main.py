"""Bodhi Phase 1 — LangGraph-powered voice interview loop."""

import os
import sys
import time
import uuid

from dotenv import load_dotenv
import sounddevice as sd
from langchain_core.messages import HumanMessage

from src.audio import get_input_device, record_until_enter, record_until_silence
from src.graph import build_interview_graph
from src.services.llm import create_llm, _extract_text
from src.services.stt import transcribe_audio
from src.services.tts import speak

load_dotenv()

VOICE_MODE = (os.getenv("BODHI_VOICE_MODE") or "natural").strip().lower()


def _init_storage():
    """Connect to NeonDB. Returns BodhiStorage or None if DATABASE_URL not set."""
    db_url = os.getenv("DATABASE_URL", "").strip()
    if not db_url:
        print("  [storage] DATABASE_URL not set — skipping NeonDB persistence.")
        return None
    try:
        from src.storage import BodhiStorage
        storage = BodhiStorage(db_url)
        storage.init_tables()
        print("  [storage] NeonDB connected.")
        return storage
    except Exception as e:
        print(f"  [storage] NeonDB connection failed: {e} — continuing without persistence.")
        return None


def _init_cache():
    """Connect to Redis. Returns BodhiCache or None if unavailable."""
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379").strip()
    try:
        from src.cache import BodhiCache
        cache = BodhiCache(redis_url)
        if cache.ping():
            print("  [cache] Redis connected.")
            return cache
        print("  [cache] Redis ping failed — continuing without cache.")
        return None
    except Exception as e:
        print(f"  [cache] Redis unavailable: {e} — continuing without cache.")
        return None


def _load_entity_context(company: str, role: str, cache, storage) -> str:
    """Load company context: Redis RAG cache -> pgvector RAG -> flat entity -> empty."""
    if not company:
        return ""

    if cache:
        cached = cache.get_rag_context(company, role)
        if cached:
            return cached

    if storage:
        try:
            from src.rag import retrieve_context
            rag_ctx = retrieve_context(company, role, storage)
            if rag_ctx:
                if cache:
                    cache.set_rag_context(company, role, rag_ctx)
                return rag_ctx
        except Exception as e:
            print(f"  [rag] Retrieval failed: {e} — falling back to flat entity.")

        entity = storage.get_entity(company)
        if entity:
            ctx = (
                f"{entity.get('description', '')} "
                f"Hiring: {entity.get('hiring_patterns', '')} "
                f"Tech: {entity.get('tech_stack', '')}"
            ).strip()
            if cache and ctx:
                cache.set_rag_context(company, role, ctx)
            return ctx

    return ""


def _flush_session(session_id, state, storage, cache):
    """Flush session data to NeonDB, contribute RAG intel, and clean up Redis."""
    transcript_text = ""
    if storage:
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
            overall = 0.0
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
                overall += s
                total_q += q

            avg_score = overall / total_q if total_q else None
            storage.end_session(session_id, overall_score=avg_score)
        except Exception as e:
            print(f"  [storage] Flush error: {e}")

    if storage and transcript_text:
        try:
            from src.rag import extract_and_contribute
            company = state.get("target_company", "")
            role = state.get("target_role", "")
            n = extract_and_contribute(company, role, transcript_text, storage)
            if n:
                print(f"  [rag] Contributed {n} chunk(s) for {company}/{role}")
        except Exception as e:
            print(f"  [rag] Contribution failed: {e}")

    if cache:
        try:
            cache.delete_session(session_id)
        except Exception:
            pass


def main() -> None:
    sarvam_key = os.getenv("SARVAM_API_KEY")
    google_key = os.getenv("GOOGLE_API_KEY")
    if not sarvam_key:
        print("Error: SARVAM_API_KEY not set. Add it to .env (see .env.example)")
        sys.exit(1)
    if not google_key:
        print("Error: GOOGLE_API_KEY not set. Add it to .env")
        sys.exit(1)

    print("Initializing Bodhi Phase 1...")
    storage = _init_storage()
    cache = _init_cache()

    llm = create_llm(api_key=google_key, model="gemini-3.1-flash-lite-preview")
    graph = build_interview_graph(llm)

    session_id = uuid.uuid4().hex[:12]
    candidate_name = os.getenv("BODHI_CANDIDATE", "Candidate")
    target_company = os.getenv("BODHI_COMPANY", "")
    target_role = os.getenv("BODHI_ROLE", "Software Engineer")

    if not target_company:
        target_company = input("Target company (or press Enter to skip): ").strip() or "General"

    entity_context = _load_entity_context(target_company, target_role, cache, storage)
    if entity_context:
        print(f"  [rag] Loaded context for {target_company} / {target_role}")

    suggested_topics = ""
    if cache:
        topics_list = cache.get_topics(target_company, target_role)
        if topics_list:
            suggested_topics = "\n".join(f"  - {t}" for t in topics_list)
            print(f"  [topics] Loaded {len(topics_list)} suggested topics")

    if storage:
        try:
            storage.create_session(session_id, candidate_name, target_company, target_role)
        except Exception as e:
            print(f"  [storage] Session create error: {e}")

    graph_config = {"configurable": {"thread_id": session_id}}

    initial_state = {
        "messages": [HumanMessage(content="Hello, I'm ready for my interview.")],
        "session_id": session_id,
        "candidate_name": candidate_name,
        "target_company": target_company,
        "target_role": target_role,
        "current_phase": "intro",
        "difficulty_level": 3,
        "phase_scores": {},
        "entity_context": entity_context,
        "suggested_topics": suggested_topics,
        "should_end": False,
    }

    dev = get_input_device()
    if dev is not None:
        print(f"Using input device: {dev}")
    else:
        default_idx = sd.default.device[0]
        devs = sd.query_devices()
        name = devs[default_idx]["name"] if default_idx < len(devs) else "default"
        print(f"Using input device: {default_idx} ({name})")

    print("=" * 50)
    print(f"Bodhi Phase 1 — Mock Interview")
    print(f"Company: {target_company} | Role: {target_role}")
    print(f"Speak in Hindi, English, or Hinglish.")
    if VOICE_MODE == "manual":
        print("Press Enter to start recording, Enter again to stop.")
    else:
        print("Just speak — stops automatically after ~1.5s silence.")
    print("Ctrl+C to exit.")
    print("=" * 50)

    result = graph.invoke(initial_state, config=graph_config)
    intro_reply = _extract_text(
        result["messages"][-1].content
        if result["messages"] and hasattr(result["messages"][-1], "content")
        else ""
    )
    if intro_reply:
        print(f"  Bodhi: {intro_reply}")
        print("Speaking...")
        speak(intro_reply, api_key=sarvam_key, target_language_code="hi-IN", speaker="shubh", play=True)
        print("Done.")

    consecutive_errors = 0
    while True:
        try:
            device = get_input_device()
            if VOICE_MODE == "manual":
                audio_bytes = record_until_enter(device=device)
            else:
                time.sleep(0.5)
                audio_bytes = record_until_silence(
                    wait_for_enter=False,
                    silence_duration_ms=1500,
                    vad_aggressiveness=3,
                    device=device,
                )
            consecutive_errors = 0

            if len(audio_bytes) < 1000:
                print("(No audio captured — try again)")
                continue

            print("Transcribing...")
            transcript = transcribe_audio(
                audio_bytes,
                api_key=sarvam_key,
                model="saaras:v3",
                language_code="en-IN",
            )
            transcript = (transcript or "").strip()
            if not transcript:
                print("(Could not transcribe — try again)")
                continue

            print(f"  You: {transcript}")

            print("Thinking...")
            result = graph.invoke(
                {"messages": [HumanMessage(content=transcript)]},
                config=graph_config,
            )

            last_msg = result["messages"][-1] if result["messages"] else None
            reply = ""
            if last_msg and hasattr(last_msg, "content"):
                reply = _extract_text(last_msg.content).strip()

            if not reply:
                print("(No response from LLM)")
                continue

            current_phase = result.get("current_phase", "?")
            print(f"  [{current_phase}] Bodhi: {reply}")

            if result.get("should_end"):
                print("Speaking...")
                speak(reply, api_key=sarvam_key, target_language_code="hi-IN", speaker="shubh", play=True)
                print("\n--- Interview Complete ---")
                _flush_session(session_id, result, storage, cache)
                break

            if cache:
                try:
                    cache.save_session_state(session_id, {
                        "phase": current_phase,
                        "difficulty": result.get("difficulty_level", 3),
                        "scores": result.get("phase_scores", {}),
                    })
                except Exception:
                    pass

            print("Speaking...")
            speak(reply, api_key=sarvam_key, target_language_code="hi-IN", speaker="shubh", play=True)
            print("Done.")

        except KeyboardInterrupt:
            print("\n--- Session interrupted ---")
            try:
                last_state = graph.get_state(graph_config)
                if last_state and last_state.values:
                    _flush_session(session_id, last_state.values, storage, cache)
                print("Session data saved. Bye.")
            except Exception:
                print("Could not flush session — exiting.")
            break
        except Exception as e:
            consecutive_errors += 1
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
            if consecutive_errors >= 3:
                print("\n3 consecutive errors — likely a device issue.")
                print("Check your mic connection or change BODHI_INPUT_DEVICE in .env")
                break

    if storage:
        storage.close()


if __name__ == "__main__":
    main()
