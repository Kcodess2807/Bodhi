# Backend Deployment — Hugging Face Spaces

How the Bodhi backend is deployed as a single self-contained Docker Space. This
documents the live setup at `https://Karush2807-bodhi-backend.hf.space`.

---

## 1. The deployment model

Hugging Face Spaces runs **one Docker container per Space** (no docker-compose)
and routes public HTTPS/WSS traffic to **one port**. That shapes three choices:

1. **Redis runs inside the container** (not external). It's only a session
   cache, so in-memory is fine.
2. **Server-side CV is dropped.** Proctoring/behavioral CV runs in the browser
   (MediaPipe WASM), so the image excludes `torch`/`transformers`/`ultralytics`/
   `mediapipe`/`deepface`. Image: ~6 GB → ~844 MB.
3. **Frontend is separate** (Vercel). Spaces aren't built for Next.js SSR.

External services stay external: **NeonDB** (Postgres), **Clerk** (auth),
**Gemini / Deepgram / Sarvam** (APIs).

```
   Vercel (Next.js)  ──HTTPS/WSS──▶  HF Space (one container)
                                       ├─ gunicorn/uvicorn  :7860
                                       └─ redis-server      :6379 (loopback)
                                          │
            ┌─────────────────────────────┼───────────────────────┐
            ▼                             ▼                         ▼
         NeonDB                  Gemini / Deepgram / Sarvam       Clerk
```

---

## 2. Deployment files (`backend/`)

These four files are the deployment artifacts. They are separate from the local
`Dockerfile` / `requirements.txt` so local docker-compose is untouched.

### `Dockerfile.hf`
Single container, slim base, Redis + API:

- Installs `redis-server` plus runtime libs for `opencv-python-headless` and
  `soundfile` (`libglib2.0-0`, `libgomp1`, `libsndfile1`).
- `COPY requirements.hf.txt → requirements.txt`, pip install.
- `COPY src/` and `start.sh`; strips CRLF from `start.sh` (authored on Windows)
  so the shebang works under Linux.
- Creates user `bodhi` (uid 1000 — HF runs containers as 1000).
- Bakes defaults: `REDIS_URL=redis://127.0.0.1:6379`, `PROCTORING_ENABLED=false`.
- `EXPOSE 7860`, `CMD ["./start.sh"]`.

### `start.sh`
```bash
redis-server --save "" --appendonly no --bind 127.0.0.1 --port 6379 &
sleep 2
exec gunicorn src.api.app:app --worker-class uvicorn.workers.UvicornWorker \
  --workers 1 --bind 0.0.0.0:7860 --timeout 120 --keep-alive 5 \
  --access-logfile - --error-logfile -
```
Redis starts in the background (in-memory, no persistence — HF storage is
ephemeral), a short sleep lets it accept connections before the app's startup
probe, then gunicorn runs in the foreground as PID 1's child.

### `requirements.hf.txt`
The slim runtime set: web stack (FastAPI/uvicorn/gunicorn), LLM/voice
(langchain/langgraph/sarvamai/websockets/soundfile), storage (psycopg/redis/
pgvector), `opencv-python-headless` + `numpy`, auth/rate-limit (pyjwt/slowapi),
reportlab. No torch/transformers/ultralytics/mediapipe/deepface.

> `cv2` is imported at module load by the proctoring router, so
> `opencv-python-headless` and `numpy` must stay even though server CV is off.

### `README.hf.md`
The Space's `README.md` with the required YAML front matter:
```yaml
---
title: Bodhi Backend
sdk: docker
app_port: 7860
---
```
`app_port` must match the gunicorn bind.

---

## 3. One-time setup

1. **Create the Space**: huggingface.co → New Space → SDK **Docker** → Blank.
2. **Write access token**: Settings → Access Tokens → create one with *write*
   permission (used as the git password).

---

## 4. Push the code

The Space is a git repo. Push the deployment files, **renaming** to the names HF
requires (`Dockerfile`, `README.md`):

```bash
git clone https://huggingface.co/spaces/<user>/bodhi-backend
cd bodhi-backend

cp -r  ../backend/src              ./src
cp     ../backend/start.sh         ./start.sh
cp     ../backend/requirements.hf.txt ./requirements.hf.txt
cp     ../backend/Dockerfile.hf    ./Dockerfile     # rename
cp     ../backend/README.hf.md     ./README.md      # rename

git add -A
git commit -m "Deploy Bodhi backend"
git push                                            # token as password
```

### Binary files (important)
HF rejects binary files that aren't in Git LFS / Xet. The repo had two that the
default `.gitattributes` doesn't track (`face_landmarker.task`, a `.png`). Since
those are **server-side CV assets that aren't used** (browser-side proctoring),
remove them before pushing:

```bash
git rm "src/proctoring_backend/services/proctoring/face_landmarker.task" \
       "src/proctoring_backend/services/proctoring/blaze_face_short_range.tflite" \
       "src/proctoring_backend/images/"*.png
```

> Never copy `backend/.env` into the Space. Secrets go in Space settings (next
> step), not the repo.

---

## 5. Set secrets

Space → Settings → Variables and secrets.

| Key | Type |
| --- | --- |
| `DATABASE_URL` | secret |
| `GOOGLE_API_KEY` | secret |
| `SARVAM_API_KEY` | secret |
| `DEEPGRAM_API_KEY` | secret |
| `CLERK_SECRET_KEY` | secret |
| `CLERK_FRONTEND_API_URL` | variable |
| `BODHI_ALLOWED_ORIGINS` | variable (frontend origin) |
| `PROCTORING_ENABLED` | variable = `false` |

**Do not set `REDIS_URL`** — the image defaults it to the in-container Redis.
Setting it (e.g. to a compose value like `redis://redis:6379`) would break the
app, since that host doesn't exist on the Space.

Secrets are injected as server-side env vars and are **never** baked into the
image or exposed publicly, even on a public Space.

Programmatic alternative (sets them from `.env` without printing values):
```python
from huggingface_hub import HfApi
api = HfApi(token="<write-token>")
api.add_space_secret("<user>/bodhi-backend", "DATABASE_URL", "<value>")
api.add_space_variable("<user>/bodhi-backend", "PROCTORING_ENABLED", "false")
```

---

## 6. Build & run on HF

- Pushing (or changing secrets) triggers a rebuild. HF builds the Dockerfile,
  then runs the container as uid 1000 on port 7860.
- The container boots Redis, waits, then gunicorn; the app lifespan connects to
  Redis (`✓ Redis connection verified`) and NeonDB, then `Application startup
  complete`.
- Watch progress in the Space **Logs** tab.

---

## 7. Verify

```bash
curl https://<user>-bodhi-backend.hf.space/health
# {"status":"ok","proctoring_enabled":false, ...}

curl -o /dev/null -w "%{http_code}\n" https://<user>-bodhi-backend.hf.space/api/companies
# 200  (confirms NeonDB connectivity)
```

`/health` reporting the CV flags as `false` is **correct** — those describe
server-side models, which are intentionally off (CV is browser-side).

---

## 8. Wire the frontend (Vercel)

1. Import the repo, root directory `client`.
2. Env: `NEXT_PUBLIC_API_URL=https://<user>-bodhi-backend.hf.space`, plus
   `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`,
   `CLERK_FRONTEND_API_URL`.
3. Deploy → get the Vercel URL.
4. Set the Space's `BODHI_ALLOWED_ORIGINS` to that URL (CORS).
5. Add the Vercel domain to Clerk → allowed origins.

WebSockets need no config — the hooks derive `wss://` from the `https://` API
URL automatically.

---

## 9. Redeploying / updating

- **Code change**: copy updated `src/` into the Space repo, commit, push → HF
  rebuilds.
- **Config change**: edit a Space secret/variable → HF restarts the container
  (no rebuild).
- **Hardware**: Settings → Hardware. CPU Basic is sufficient (no server-side ML;
  the backend is I/O-bound on the external APIs).

---

## 10. Operational notes

- **Free tier sleeps** after idle (~48h); the first request cold-starts it
  (~30s).
- **Ephemeral state**: in-container Redis + in-memory checkpointer mean session
  cache and active interview state are lost on restart. All durable data
  (sessions, reports, resumes, transcripts) is in NeonDB.
- **Public Space**: safe — secrets are server-side, endpoints are Clerk-JWT
  gated, rate-limited, and CORS-locked. FastAPI `/docs` is publicly listable but
  still auth-gated to call.

---

## 11. Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| Push rejected: "contains binary files" | Untracked binary not in LFS/Xet — remove the unused CV asset (§4) or add to LFS. |
| App boots but DB calls 500 | `DATABASE_URL` missing/wrong in Space secrets. |
| Redis connection refused | `REDIS_URL` was set to a non-loopback host — unset it so the in-container default applies. |
| `start.sh: bad interpreter` | CRLF line endings — the Dockerfile strips them with `sed -i 's/\r$//'`. |
| CORS errors in the browser | `BODHI_ALLOWED_ORIGINS` doesn't include the frontend origin. |
| 503 on `/api/interviews/prepare` | Redis unavailable — check the Logs tab for the Redis startup line. |
