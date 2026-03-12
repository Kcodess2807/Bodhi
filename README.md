# Bodhi
Building a voice-first, low-latency AI Mock Interviewer is a massive technical undertaking. Since you are moving away from simple orchestration toward a full-scale speech-driven system with integrated coding and persistent memory, the feature set needs to be industrial-grade.

Here is the comprehensive documentation for the features and technical integration of your **Hinglish AI HR System**.

---

## Tech Stack (Backend)

* **Language:** Python
* **API Framework:** FastAPI — high-performance, async delivery layer for WebSocket streaming, REST endpoints, and horizontal scaling.
* **AI Orchestration:** LangChain + LangGraph — LangGraph as the primary orchestration layer; LangChain for sub-flows (prompts, RAG). Google Gemini API powers the LLM.
* **Speech SDKs:** Sarvam AI — `sarvamai` Python package (`pip install sarvamai`). Saaras V3 for STT, Bulbul V3 for TTS. Both support WebSocket streaming for low latency.
* **Additional Resources:** Pydantic (validation), Uvicorn (ASGI server), `sounddevice` or `pyaudio` for live mic capture (CLI phase).

---

## API Keys (Environment Variables)

| Service | Env Variable | Usage |
| --- | --- | --- |
| **Sarvam AI** | `SARVAM_API_KEY` | Passed as `api_subscription_key` to `AsyncSarvamAI`. Used for Saaras (STT) and Bulbul (TTS). |
| **Google Gemini** | `GOOGLE_API_KEY` or `GEMINI_API_KEY` | Used by `langchain-google-genai` / `ChatGoogleGenerativeAI` for LLM responses. |

---

## Phase 0: CLI Voice Loop (Current Scope)

* **Goal:** Run from terminal → speak (Hindi/English/Hinglish) → hear AI response. No web frontend.
* **Flow:**
  1. **Mic capture** → Raw audio chunks (WAV or PCM, 16kHz) from local microphone via `sounddevice` or `pyaudio`.
  2. **Saaras V3 (STT)** → Sarvam streaming API (`client.speech_to_text_streaming.connect` with `model="saaras:v3"`). Use `mode="codemix"` for Hinglish or `mode="transcribe"` for single-language. VAD (voice activity detection) or manual flush to determine end-of-utterance.
  3. **LangChain + LangGraph + Gemini** → Transcribed text → Gemini via `ChatGoogleGenerativeAI` → generates reply. LangGraph orchestrates flow (for now, a minimal graph or simple chain).
  4. **Bulbul V3 (TTS)** → Sarvam streaming API (`client.text_to_speech_streaming.connect` with `model="bulbul:v3"`). Configure `target_language_code` (e.g., `hi-IN`, `en-IN`) and `speaker` (e.g., `shubh`). Stream audio chunks back.
  5. **Playback** → Output audio to speakers (e.g., via `sounddevice`, `pyaudio`, or `pygame`).
* **Sarvam SDK Notes:**
  - **STT:** `AsyncSarvamAI` → `speech_to_text_streaming.connect(model="saaras:v3", mode="codemix", language_code="hi-IN", high_vad_sensitivity=True)`. Audio formats: WAV or raw PCM (`pcm_s16le`). Sample rate must match in connection and `transcribe()` call (16kHz recommended).
  - **TTS:** `text_to_speech_streaming.connect(model="bulbul:v3")` → `configure(target_language_code, speaker)` → `convert(text)` → `flush()` → iterate `async for message in ws` for `AudioOutput` chunks (base64-decoded). Speakers: Shubh, Aditya, Ritu, Priya, etc. Languages: `hi-IN`, `en-IN`, and 9 other Indian languages.

### Running Phase 0

```bash
# 1. Create .env and add your API keys (copy from .env.example)
#    SARVAM_API_KEY=...
#    GOOGLE_API_KEY=...

# 2. Create a virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the voice loop (from project root)
python -m src.main
```

**Flow:** Press Enter → start recording → speak (Hindi/English/Hinglish) → Press Enter to stop → transcript → Gemini reply → TTS playback. Repeat. Ctrl+C to exit.

---

## 1. Speech Stack (The Voice Layer)

To achieve "Rapid Manner" responses with minimal latency, we will use a **streaming architecture** rather than a batch (request-response) one.

* **STT: Saaras V3 (Streaming Mode):**
* **Real-time Transcription:** Unlike standard STT that waits for a sentence to end, Saaras V3 allows for "incremental decoding." The AI starts "thinking" about the response while the user is still finishing their sentence.
* **Hinglish Mastery:** Native support for code-mixing (e.g., *"Mera experience Java backend mein hai"*).


* **TTS: Bulbul V3 (Expressive Voice):**
* **Telephony Grade Audio:** Optimized for 8kHz/16kHz to ensure the HR's voice sounds like a real phone/web call.
* **Prosody Control:** It supports contextual pauses and emphasis, so the HR doesn't sound like a robot when asking difficult questions.
* **Bilingual Output:** Can switch between Hindi and English mid-sentence without changing the voice font.



---

## 2. Dynamic Question "Doctor" System

Instead of a static list, this system "diagnoses" the user's needs to curate a custom interview.

* **Company-Specific Scraper/Engine:** You will feed the system data on specific hiring patterns (e.g., Google's focus on Go/Algorithms vs. a startup's focus on React/Product).
* **Resume-Job Description (JD) Mapping:** The "Doctor" module compares the user's uploaded resume against the company's target role to find "weak spots" and target them with questions.
* **Difficulty Scaling:** If the user answers perfectly, the system automatically increases the technical depth (e.g., moving from "What is an Index?" to "How does a B-Tree handle concurrent writes?").

---

## 2a. Intelligence Device (RAG System)

A **Retrieval Augmented Generation (RAG)** system maintains a persistent entity knowledge base that keeps the interview grounded and company-specific.

* **Entity Knowledge Base:** Users contribute information about entities (companies, roles, domains)—e.g., *"Just Payments is a company focused on technical payment solutions"*—which is stored in the database and indexed for retrieval.
* **Crowdsourced + Latest Data:** When another user preps for a similar entity, the system retrieves pre-existing data plus the latest contributions to build accurate, up-to-date interview content. No stale or fragmented intelligence.
* **Feeds the Question Doctor:** The RAG layer augments the Question Doctor with company-specific patterns, hiring focus, and technical expectations—so questions reflect real-world targets (Google, Meta, startups, etc.).
* **Implementation:** LangChain orchestrates the RAG pipeline (embedding, vector store, retrieval). Vector storage (e.g., Chroma, FAISS, or pgvector in PostgreSQL) enables semantic search over entity and interview data.

---

## 3. LangChain & LangGraph Workflow Orchestration

The interview flow is **not linear**. The AI must decide when sections end, transition between rounds, and invoke features (e.g., code editor) dynamically. This requires a **stateful graph**, not a simple chain.

* **LangGraph State Machine:** The interview is modeled as a directed graph with explicit state. Nodes represent phases (e.g., *General/Behavioral Round*, *Technical Round*, *Coding Round*). Edges define transitions; conditional edges route based on the AI's decision.
* **Section Transitions:** When the AI concludes the general/behavioral round and decides to move to technical rounds, that decision updates the graph state. The transition is persisted, so the system never "forgets" which phase the user is in.
* **Tool Invocation:** The AI can call tools as graph nodes—e.g., `pull_up_code_editor` when it decides to start the coding round. LangGraph routes to the tool node, executes it (which surfaces the Monaco editor to the user), and returns control to the conversational flow.
* **LangChain Integration:** LangChain handles linear sub-flows (RAG retrieval, prompt assembly). LangGraph orchestrates the higher-level, branching workflow—when to ask, when to evaluate, when to switch rounds, when to invoke the code editor.
* **Why Both:** LangChain = modular, stateless chains (RAG, prompts). LangGraph = cyclic, stateful workflows with loops, branches, and tool calls. Together they enable an interview that adapts in real time.

---

## 4. Real-Time Coding Editor & Evaluator

A side-by-side terminal where the AI acts as a "Senior Pair Programmer."

* **Collaborative Editor:** Integrated **Monaco Editor** (the engine behind VS Code).
* **Live Code Analysis:** As the user writes, the system doesn't just check if the code *runs*; it checks for:
* **Logic Errors:** Identifies infinite loops or edge-case failures.
* **Complexity Analysis:** Gives feedback on $O(n)$ vs $O(n^2)$ efficiency.


* **The "Nudge" Mechanism:** If the user is stuck, the AI won't give the answer immediately. It will provide a "hint" (e.g., *"Aap yahan Hashmap use karke time complexity kam kar sakte hain"*).

---

## 5. Persistent Memory & Rapid Database Sync

For a **50-minute session**, the AI cannot lose track of what was said at minute 5.

* **Continuous Context Window:** We will use **Gemini 1.5 Flash** due to its 1-million+ token context window. It will literally "remember" the entire 50-minute transcript without needing summarization.
* **Rapid Database (PostgreSQL/Firebase):** Every spoken word and every keystroke in the code editor is synced to a **PostgreSQL** or **Firebase** database every 500ms.
* **Post-Interview Analytics:** After the session, the database generates a "Heatmap" of the user's performance—where they stuttered, where their code failed, and where they were most confident.



---

## 6. HR Persona & Behavioral Intelligence

The "HR Bot" is programmed to be a "tough but fair" interviewer.

* **Situational Awareness:** If the user gives a vague answer, the bot is instructed to "double down" (e.g., *"That's a good start, but can you give me a specific instance where you handled a conflict in your team?"*).
* **Likhit (Written) + Shrut (Oral) Feedback:** While the conversation is voice-based, a real-time sidebar provides written "Interviewer Notes" so the user can see live feedback on their tone or technical accuracy.

---

### Feature Summary Table

| Feature | Technology | Primary Benefit |
| --- | --- | --- |
| **Backend** | Python + FastAPI | Async API, WebSocket streaming, production-ready delivery. |
| **Phase 0 Voice** | Sarvam SDK (Saaras + Bulbul) + Gemini | CLI: speak → transcribe → Gemini reply → TTS playback. |
| **Orchestration** | LangChain + LangGraph | Stateful workflow; section transitions; tool invocation (e.g., code editor). |
| **Intelligence Device** | RAG + Entity DB | Crowdsourced company/role data; grounds interviews in real hiring patterns. |
| **Bilingual Voice** | Saaras V3 + Bulbul V3 | Natural, low-latency Hinglish conversation. |
| **Code Editor** | Monaco + Gemini Evaluator | Real-time code feedback and "Hints." |
| **Context Memory** | 1M Token Window | Remembers the full 50-minute session. |
| **Rapid Sync** | WebSocket + PostgreSQL/Firebase | Zero data loss; sub-second state updates. |
| **Question Doctor** | RAG + Company Data | Curated questions for specific firms (Google, Meta, etc.). |

---

## Questions Before Implementation

1. **Saaras vs Cyrus:** You mentioned "Cyrus V3 from Servum" — the Sarvam API docs refer to **Saaras V3**. Are these the same, or do you have a different STT provider in mind?

2. **STT mode:** For "my personal language" (Hindi or English), should we use `codemix` (Hinglish), `transcribe` (single language with `language_code`), or auto-detect based on user preference?

3. **TTS speaker & language:** Preferred Bulbul speaker (e.g., Shubh, Priya, Aditya)? Should TTS mirror the user's input language, or always output in a fixed language (e.g., Hinglish)?

4. **End-of-speech trigger:** For CLI, how should we detect "user finished speaking"? Options: (a) VAD + silence (Sarvam's `high_vad_sensitivity` + `speech_end`), (b) manual push-to-talk (press key to stop), or (c) fixed timeout after last speech?

5. **Gemini model:** Use `gemini-1.5-flash` (faster, cheaper, 1M context) or `gemini-1.5-pro` (smarter, slower)? Or `gemini-2.0-flash` if available in your region?

6. **Persona in Phase 0:** For the initial CLI loop, should the AI already behave as the "HR interviewer" (tough but fair), or as a generic conversational assistant for now?

---

**Next Step:**
Would you like me to create the **detailed JSON Schema** for the Database so you can see exactly how the 50-minute context, entity/RAG data, and coding scores will be stored?