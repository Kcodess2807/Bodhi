# Bodhi Backend

Reference for the FastAPI backend under `backend/`. Covers the architecture,
the live interview pipeline, proctoring, behavioral metrics, storage, config,
and deployment.

---

## 1. Overview

The backend is a FastAPI app that runs the interview: it authenticates the
candidate, loads company/role/resume context, drives a LangGraph "brain" over
Google Gemini, and streams a real-time voice loop (Deepgram STT in, Sarvam TTS
out) over a WebSocket. Proctoring and behavioral CV run in the browser; the
backend persists what they report and generates the final report.

```
┌─────────────┐   HTTPS / WSS   ┌───────────────────────────┐    ┌──────────┐
│  Next.js UI │ ───────────────▶│  FastAPI (gunicorn/uvicorn)│───▶│  Gemini  │
│  (client/)  │ ◀───────────────│  LangGraph orchestration   │◀───│   LLM    │
└─────────────┘                 └───────────┬───────────────┘    └──────────┘
       │  raw PCM-16 / events               │
       │                          ┌─────────┼──────────┬──────────────┐
       │                          ▼         ▼          ▼              ▼
       │                     ┌─────────┐ ┌──────┐ ┌─────────┐  ┌────────────┐
       └────────────────────▶│ Deepgram│ │Sarvam│ │ NeonDB  │  │   Redis    │
         browser CV events   │  STT    │ │ TTS  │ │(pgvector)│ │ (cache)    │
                             └─────────┘ └──────┘ └─────────┘  └────────────┘
```

---

## 2. Tech stack

| Concern | Choice |
| --- | --- |
| Web framework | FastAPI + gunicorn (1 uvicorn worker) |
| Orchestration | LangGraph (`StateGraph`) |
| LLM | Google Gemini (`gemini-3.1-flash-lite-preview`) via `langchain-google-genai` |
| STT (live) | Deepgram Nova-3 streaming WebSocket |
| TTS (live) | Sarvam Bulbul v3, linear16 over a persistent WebSocket |
| DB | NeonDB Postgres + pgvector (`psycopg2` / `psycopg`) |
| Cache | Redis |
| Auth | Clerk JWT |
| Rate limiting | slowapi |
| Proctoring / behavioral CV | Browser-side MediaPipe (WASM); backend only persists |

---

## 3. Module layout (`backend/src`)

```
api/
  app.py          App factory, lifespan, CORS, router registration, /health
  auth.py         Clerk JWT verification (HTTP dep + WS query-token)
  deps.py         FastAPI dependencies (storage, cache, llm, keys, require_auth)
  interviews.py   Interview lifecycle + the live voice WebSocket
  proctoring.py   Proctoring WebSocket (browser-CV persistence)
  resumes.py      Resume upload, parsing, ATS scoring
  users.py        User profile sync/status
  roles.py        Role profiles
  companies.py    Company profiles / entities
  documents.py    Company doc ingestion (RAG)
  audio.py        Misc audio endpoints
  models.py       Pydantic request/response models
  concurrency.py  run_blocking + timeouts for blocking I/O
  limits.py       Max body / audio / editor / WS frame sizes
  ratelimit.py    slowapi setup

graph.py          LangGraph build: interviewer node, tools, checkpointer
state.py          InterviewState TypedDict + PHASE_CONFIG
prompts.py        System prompts (standard / resume / JD-targeted)
tools.py          LangGraph tools (score, transition, difficulty, end)
memory.py         Phase memory compaction + cross-section context
report.py         Report generation (scores, behavioral, proctoring summary)
rag.py            Retrieval + contribution
embeddings.py     Gemini embeddings
storage.py        NeonDB access layer (thread-local pool)
cache.py          Redis cache (initial state, session state, RAG, queues)
resume_parser.py  Resume → structured profile, gap map
ats.py            Resume quality + JD-match scoring
document_parser.py PDF/DOCX extraction

services/
  llm.py          create_llm, _extract_text (Gemini 3.x list-content handling)
  stt_deepgram.py DeepgramStreamingSTT (live)
  stt.py          Batch STT (Sarvam) for non-live paths
  tts.py          SarvamTTSStream (persistent linear16) + helpers
  sentiment.py    Rule-based tone (fillers/hedges/markers)
  behavioral.py   Per-turn speech metrics (WPM, filler, confidence, tone)
```

`behavioral_analysis/` and `proctoring_backend/` hold the legacy server-side CV
stack. It is **not loaded** in normal operation (`PROCTORING_ENABLED=false`) and
is excluded from the deployment image.

---

## 4. Authentication

- HTTP routes depend on `require_auth`, which verifies the Clerk JWT from the
  `Authorization: Bearer <token>` header and returns the `clerk_user_id`.
- WebSockets can't set headers in the browser, so the token is passed as a
  `?token=<jwt>` query param and verified by `authenticate_websocket` **before**
  the socket is accepted.
- Ownership: interview and proctoring sockets check that the authenticated user
  owns the session (`sessions.clerk_user_id`). Non-owners get a 404/close, not a
  403, so the existence of a session isn't leaked.

---

## 5. Interview lifecycle

### Prepare (HTTP)
`POST /api/interviews/prepare` →
1. Resolve the owned resume profile (if resume mode).
2. Load entity/role context + RAG, suggested topics.
3. Pre-generate a curriculum (2 technical + 2 DSA questions) unless resume mode.
4. `create_session(...)` in NeonDB.
5. Save the initial state to Redis (`initial:<session_id>`).
6. Return `session_id`.

### Live voice loop (WebSocket)
`WS /api/interviews/{session_id}/ws?token=<jwt>`:

```
auth + ownership ──▶ accept ──▶ load initial state from Redis
   │
   ├─ greeting: graph.invoke() → reply text → SarvamTTSStream → client (PCM-16)
   │
   └─ loop:
        client streams raw PCM-16 ──▶ DeepgramStreamingSTT
        Deepgram utterance_end ─────▶ run_turn(transcript, speech_duration)
             ├─ behavioral metrics (compute_speech_behavioral) → save + send
             ├─ _session_pipeline_audio: graph.invoke() → reply text
             │      └─ split into sentences → SarvamTTSStream → client (PCM-16)
             └─ reply_complete {phase, should_end, sentiment}
        on should_end ─────────────▶ _flush_session_sync (report) → close
```

Key points:

- **`graph.invoke()` not `astream_events`.** The interviewer node is a sync
  function; LangGraph runs sync nodes in a threadpool where the chat-model
  callbacks `astream_events` relies on never fire, so the reply text never
  reached TTS (the turn "froze"). Gemini is non-streaming anyway, so invoke
  loses nothing.
- **TTS** is one persistent linear16 Sarvam WebSocket per session. Audio is sent
  to the client as raw PCM-16; the browser plays it via the Web Audio API (no
  MP3 decode).
- **Barge-in**: an `interrupt` control cancels the in-flight turn and drops
  pending TTS audio.
- **Speaking duration** is measured from the first interim transcript to
  `utterance_end` (minus Deepgram's trailing-silence window) for WPM.

### Control messages (client → server)
`speech.start`, `interrupt`, `proctor_alert` (triggers the verbal "relax" line),
`ping`.

### Control events (server → client)
`session_config`, `greeting_start`, `greeting_complete`, `interim_transcript`,
`transcript`, `text_chunk`, `reply_complete`, `interrupted`, `reassurance`,
`pong`.

---

## 6. LangGraph orchestration

`build_interview_graph(llm, checkpointer)` compiles:

```
interviewer ──(tools_condition)──▶ tools ──▶ process_tools ──┬─▶ compact_memory ──▶ interviewer
     ▲                                                       └─▶ interviewer
     └──────────────────────────── END (no tool call) ───────────────────────
```

- **interviewer**: builds the system prompt for the mode/phase and calls
  `model.bind_tools(ALL_TOOLS).invoke(...)`.
- **tools** (`ToolNode`): the model calls tools that emit machine-readable
  strings (`SCORE:...`, `TRANSITION:...`, `DIFFICULTY:...`, `END:...`).
- **process_tools** (`_process_tool_results`): parses those, updates
  `phase_scores`, `answer_scores`, difficulty, pops the next queued question,
  handles probing and phase transitions.
- **compact_memory**: on a phase transition, LLM-summarizes the prior phase into
  `phase_memories` for cross-section context.

State is `InterviewState` (`state.py`); phases and per-phase question targets in
`PHASE_CONFIG`.

### Checkpointer
`create_durable_checkpointer()` returns a Postgres saver **only** if
`DURABLE_CHECKPOINTER=true`; otherwise the graph uses in-memory `MemorySaver`.
The sync `PostgresSaver` is incompatible with async streaming, and durable state
isn't required since the live path uses `invoke`. **Implication:** interview
state is per-worker and lost on restart (all durable data is in NeonDB).

---

## 7. Proctoring

CV runs in the **browser** (`client/hooks/useProctoring.ts`, MediaPipe WASM).
The backend's job is persistence and the report.

`WS /api/proctoring/ws/{session_id}`:

- If server-side models aren't loaded (`PROCTORING_ENABLED=false`), the handler
  runs `_run_browser_proctoring` — it does **not** import the CV stack (importing
  mediapipe/torch on connect was segfaulting the worker). It accepts these
  messages:
  - `client_violation` → `proctoring_violations` (type, severity, message).
    Session is flagged after 8 reported violations.
  - `client_behavioral` → `sentiment_data` (facial emotion, posture, gaze).
  - `ping` / `end_session`.

Browser-detected signals: no-face, multiple-people, phone, unauthorized object,
head-pose + iris gaze ("looking away"), tab-switch, focus-loss, fullscreen-exit,
clipboard copy/paste. All are temporally debounced (must persist N frames).

A sustained high violation rate makes the client send `proctor_alert` on the
interview socket, which makes Bodhi speak a short reassurance line (cooldown
applied).

---

## 8. Behavioral metrics

`services/behavioral.py::compute_speech_behavioral(transcript, duration_sec)`
runs per answer and returns: `emotion`, `sentiment`, `speaking_rate_wpm`,
`filler_rate`, `confidence_score`, `flags`.

- Reuses the rule-based `analyze_tone` (fillers, hedges, vocal-tone label).
- WPM from word count / measured speaking duration.
- Confidence is a transparent 0–100 formula (filler penalty + ideal-pace band +
  answer length + hedging).
- Deepgram runs with `filler_words=true` so "um/uh" survive in the transcript.

Results are saved to `sentiment_data` and sent in the `reply_complete` payload
(live Sentiment panel). Facial emotion / posture / gaze come from the browser
via `client_behavioral`. `report.py::_build_behavioral_summary` aggregates both
sources into the report's Behavioral Analytics.

---

## 9. Storage (NeonDB)

Main tables (`storage.py`):

| Table | Purpose |
| --- | --- |
| `sessions` | One row per interview (owner, company, role, scores, report_data) |
| `user_profiles` | Resume profile + `resume_file_content BYTEA`, name, experience |
| `transcripts` | Per-message transcript, batched on flush |
| `proctoring_violations` | Browser-reported violations |
| `sentiment_data` | Per-turn speech metrics + browser behavioral samples |
| `entities` / `company_documents` / `role_profiles` | RAG context |

Notes:
- Connection pooling is thread-local (one connection per worker thread).
- pgvector is used for RAG embeddings.
- Resume files are stored in the DB (BYTEA), not on disk — nothing durable lives
  on the container filesystem.

---

## 10. Cache (Redis)

`cache.py` stores:
- `initial:<session_id>` — the prepared interview setup (consumed by the WS).
- session state (phase / difficulty / scores) for quick reads.
- RAG context and pre-generated question queues.

Required at runtime — `prepare` returns 503 if Redis is unavailable.

---

## 11. Reliability controls

- **Auth** on every route + WS (Clerk JWT) with per-session ownership checks.
- **Rate limiting** via slowapi (`ratelimit.py`), default 120/min, memory store.
- **Input limits** (`limits.py`): max body, audio, editor text, WS frame size.
- **Timeouts** (`concurrency.py`): blocking I/O (STT/TTS) wrapped in
  `run_blocking` with hard timeouts so a hung upstream can't stall a turn.
- **CORS**: origins from `BODHI_ALLOWED_ORIGINS` (comma-separated); defaults to
  `localhost:3000` / `5173`.

---

## 12. Report generation

On interview end (`should_end` or `POST /{id}/end`), `_flush_session_sync`:
1. Saves the transcript batch.
2. Aggregates phase scores → overall.
3. `report.generate_report(...)` builds phase breakdown, behavioral summary,
   proctoring summary, cross-section insights, hiring recommendation (agentic
   fields via Gemini).
4. `end_session(... report_data=...)` persists it; RAG contribution runs;
   Redis session is cleared.

`GET /api/interviews/{id}/report` returns it (and `/report/pdf` renders a PDF via
reportlab). Generation is async/blocking and takes ~10–20s, so the frontend
polls the report endpoint until it's ready.

---

## 13. Configuration (env)

| Key | Required | Notes |
| --- | --- | --- |
| `DATABASE_URL` | yes | NeonDB Postgres |
| `REDIS_URL` | yes | defaults to in-container Redis in the HF image |
| `GOOGLE_API_KEY` | yes | Gemini + embeddings |
| `SARVAM_API_KEY` | yes | TTS |
| `DEEPGRAM_API_KEY` | yes | STT |
| `CLERK_SECRET_KEY` | yes | JWT verification |
| `CLERK_FRONTEND_API_URL` | yes | Clerk issuer |
| `BODHI_ALLOWED_ORIGINS` | prod | frontend origin(s), comma-separated |
| `PROCTORING_ENABLED` | — | `false` (browser-side CV) |
| `DURABLE_CHECKPOINTER` | — | `true` to enable PostgresSaver (off by default) |
| `SARVAM_TTS_*`, `DEEPGRAM_*`, `LLM_*` | — | model/voice/timeout overrides |

---

## 14. Deployment

### Hugging Face Spaces (single self-contained image)
- `backend/Dockerfile.hf` builds one image running **Redis + the API** (via
  `start.sh`): Redis in-memory on loopback, gunicorn on `:7860`, uid 1000.
- `backend/requirements.hf.txt` is the slim set — server-side CV deps
  (`torch`/`transformers`/`ultralytics`/`mediapipe`/`deepface`) are dropped since
  proctoring is browser-side. Keeps `opencv-python-headless` + `numpy`. Image is
  ~844 MB (vs ~6 GB).
- On the Space repo the files must be named `Dockerfile` and `README.md`; the
  Dockerfile `COPY`s `requirements.hf.txt`.
- Secrets are set as Space env (server-side, not in the image). `REDIS_URL` is
  left unset so the in-container default applies.
- `app_port: 7860` in the Space README; WS upgrades to `wss://` off HTTPS.

### Local (docker-compose)
`backend/docker-compose.yml` runs the API (heavy `Dockerfile`) + a separate
Redis service, with `./src` bind-mounted for fast iteration. Host port via
`API_HOST_PORT` (8001 locally).

---

## 15. Known trade-offs

- In-memory checkpointer + in-container Redis → session/cache state is ephemeral
  across restarts. Durable data (sessions, reports, resumes, transcripts) is all
  in NeonDB.
- Single worker; scale horizontally (more containers), not vertically.
- Free-tier Spaces sleep on idle (~30s cold start).
- Report generation is async (~10–20s); the frontend polls.
