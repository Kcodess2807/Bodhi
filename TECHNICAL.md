# Bodhi — Technical Roadmap

Internal reference document. Not for external distribution.

## Current Architecture

```
┌─────────────┐     ┌──────────────────────┐     ┌──────────┐
│  Next.js UI  │────▶│  FastAPI (30+ routes) │────▶│  Gemini  │
│  (client/)   │◀────│  LangGraph orchestr.  │◀────│  LLM     │
└─────────────┘     └──────────┬───────────┘     └──────────┘
                               │
               ┌───────────────┼───────────────┐
               │               │               │
        ┌──────▼──────┐ ┌─────▼──────┐ ┌──────▼──────┐
        │   Redis     │ │  NeonDB    │ │  Sarvam AI  │
        │  (cache +   │ │ PostgreSQL │ │  STT / TTS  │
        │  Q queues)  │ │ + pgvector │ │             │
        └─────────────┘ └────────────┘ └─────────────┘
```

**Data flow**: User speaks → browser VAD detects speech → raw PCM encoded to WAV → sent to backend via WebSocket → Sarvam STT → LangGraph processes turn. 
**Streaming**: `astream_events` generates tokens. We filter for `langgraph_node="interviewer"` to prevent background LLM events (like memory compaction) from leaking into the transcript. If `[END_INTERVIEW]` is detected, the pipeline sets `should_end=True` and strips the token from voice and text outputs. 
LangGraph processes turn → Gemini generates reply token-by-token → Sentence accumulator catches punctuation → Sarvam TTS per sentence → audio chunks streamed back over WebSocket → auto-play → loop.

**Storage tiers**: MemorySaver (in-process, zero latency) → Redis (sub-ms cache for session snapshots, entity context, suggested topics, **question queues**, **phase memories**) → NeonDB PostgreSQL (permanent: sessions, transcripts, phase results, company profiles, role profiles, vector embeddings, **phase memories**, **answer scores**).

**RAG pipeline**: Documents ingested → chunked → embedded with Google gemini-embedding-001 (3072-dim) → stored in pgvector → retrieved via cosine similarity at interview start and enriched with role profiles.

---

## Interview Hub Flow

```
Document Upload → extract_profile_data() → company_profiles + entities (NeonDB)
                                                 │
Resume Upload ─── parse_resume() ────────────────┼──▶ user_profiles (NeonDB)
                                                 │
Interview Pre-flight ─ POST /prepare ────────────┼──▶ generate_interview_curriculum()
               └─── mode, user_id (optional) ────┼──▶ gap_map generation
                                                 │         │
                                         profile_text      │
                                                           ▼
                                                   Gemini LLM generates
                                                   2 technical + 2 DSA Qs
                                                           │
                                                           ▼
                                                    Redis initial_state & Qs
                                                           │
Frontend Connects ─ WS /ws/{id} ───────────────────────────┘
                                                           │
                                                           ▼
                                              LangGraph invokes turn
                                                           │
                                    On TRANSITION/SCORE ───▶ target_question popped
                                                           │
                                                           ▼
                                              Injected into system prompt
                                              as TARGET QUESTION block
```

### Interview Modes
1. **Standard** (`mode="standard"`): Classic interview using company/role documents + generated curriculum.
2. **Resume-Based** (`mode="option_a"`): Personalized using extracted candidate profile.
3. **JD Gap Analysis** (`mode="option_b"`): Highly targeted interview based on resume profile vs. JD text gaps.

### Phase Flow

`intro` → `technical` → `behavioral` → `dsa` → `project` → `wrapup`

| Phase | Pre-decided Qs | Target Qs | Max Qs | Target Min | Behavior |
|-------|----------------|-----------|--------|------------|----------|
| Intro | None (ad-hoc) | 3 | 4 | 3 | Greeting + ask candidate to self-introduce |
| Technical | 2 questions | 5 | 7 | 12 | Domain concepts, language internals, system design |
| Behavioral | None (ad-hoc) | 4 | 5 | 8 | STAR-method, leadership, teamwork |
| DSA | 2 questions | 3 | 4 | 10 | Algorithms, data structures, complexity analysis |
| Project | None (ad-hoc) | 3 | 4 | 8 | Past projects, architecture, trade-offs |
| Wrapup | None (ad-hoc) | 2 | 3 | 4 | Summary, feedback, candidate questions |

Total target: **~45 minutes** across all phases.

---

## Context Memory Architecture

```
Phase transition (e.g., technical → behavioral):

  1. compact_memory node fires
  2. LLM summarises completed phase → structured JSON:
     {
       "key_claims": ["Used Redis for caching at scale", ...],
       "strengths": ["Strong distributed systems knowledge"],
       "weaknesses": ["Vague on database indexing"],
       "follow_up_hooks": ["Probe Redis cache invalidation strategy"],
       "topics_covered": ["caching", "microservices", "gRPC"],
       "notable_quotes": ["I built a system handling 10M requests/day"]
     }
  3. Stored in Redis: memory:{session_id}:{phase}
  4. Injected into next phase's system prompt as CROSS-SECTION CONTEXT
  5. Follow-up hooks become probing directives

At session end:
  - All phase memories flushed to NeonDB (phase_memories table)
  - All answer scores flushed to NeonDB (answer_scores table)
  - **Report Agent Pipeline**: Total transcript + behavioral summaries are sent to a dedicated LLM Agent (`src/agents/report_agent.py`) which synthesizes the final hiring recommendation, qualitative strengths, and cross-section insights.
  - Final structured report is compiled from Agent+Deterministic data.
```

### Graph Flow (with Memory)

```
  interviewer → tools → process_tools ─┬─ (TRANSITION) → compact_memory → interviewer
                                       └─ (else) → interviewer
```

### Multi-Dimensional Scoring

Every answer is scored on 4 axes (1-5 each):

| Dimension | Weight | What it measures |
|-----------|--------|------------------|
| Accuracy | 30% | Factual correctness |
| Depth | 25% | Trade-offs, edge cases, alternatives |
| Communication | 20% | Clarity and structure |
| Confidence | 15% | Certainty vs. guessing |

Composite = weighted average. Mapped to percentage → letter grade (A+ to F).

If any dimension ≤ 2, or the answer seems vague, `needs_probing` is set and the bot must challenge before moving on.

### NeonDB Schema Additions

```sql
phase_memories (session_id, phase, summary JSONB)
answer_scores  (session_id, phase, question_num, accuracy, depth, communication, confidence, composite, feedback, probed, probe_reason)
```

---

## Next Priorities

### 1. Proctoring System

Camera-based monitoring during interviews to ensure candidate authenticity.

**Implementation plan:**

- Use `navigator.mediaDevices.getUserMedia({ video: true })` to access the webcam
- Display a small self-view preview in the interview UI corner
- Run face detection at regular intervals (every 2-3 seconds) using a lightweight model:
  - Option A: TensorFlow.js `blazeface` — runs entirely in-browser, no server round-trips
  - Option B: `face-api.js` — higher accuracy, slightly heavier
- Track and flag suspicious behavior:
  - Face not detected for more than N seconds
  - Face looking away (head pose estimation) for extended periods
  - Multiple faces detected
- Show a visual indicator (green dot = proctor active, yellow = warning, red = violation)
- Log proctor events to the backend as part of the session record
- Violations can optionally pause the interview or append a warning to the LangGraph state

**Key constraints:**

- All detection should happen client-side to avoid latency
- Camera permission must be requested and granted before interview starts
- If camera access is denied, interview can still proceed but will be flagged as "unproctored"

### 2. Focus Mode

Prevent candidates from switching tabs or windows during an active interview.

**Implementation plan:**

- Listen to `document.visibilitychange` events to detect tab switches
- Listen to `window.blur` events to detect window focus loss
- On violation:
  - Show a full-screen overlay warning ("Please return to the interview tab")
  - Log the event with timestamp to the backend
  - Increment a violation counter displayed in the session sidebar
  - After N violations (configurable, e.g. 3), optionally auto-end the interview
- The focus lock should only be active between interview start and end
- On interview end, release all focus tracking listeners

**Key constraints:**

- Cannot truly prevent tab switching (browser limitation), but can detect and respond
- Must not interfere with browser audio permissions or mic access
- Should work across Chrome, Firefox, and Edge

---

## Future Considerations

- **Code editor integration**: Embed a Monaco/CodeMirror editor for live coding rounds, triggered by LangGraph tool call
- **Multi-language STT**: Re-enable Hindi/Hinglish transcription once Sarvam model support stabilizes
- **Session replay**: Record full audio + transcript for post-interview review
- **Analytics dashboard**: Aggregate scores, common weak areas, improvement tracking across sessions, leveraging the new multi-dimensional scoring data
- **Interview Hub frontend**: Search by company + role, browse curated interviews, view community-sourced prep materials
- **Report sharing**: Generate shareable PDF/HTML reports from the `report.py` output
