---
title: Bodhi Backend
emoji: 🧘
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# Bodhi Backend

FastAPI interview backend (LLM + voice pipeline + browser-side proctoring).
Redis runs inside the container; bring your own NeonDB, Clerk, and API keys via
Space secrets.

## Required secrets / variables

Set under Space Settings → Variables and secrets:

| Key | Type | Notes |
| --- | --- | --- |
| `DATABASE_URL` | secret | NeonDB Postgres URL |
| `GOOGLE_API_KEY` | secret | Gemini |
| `SARVAM_API_KEY` | secret | TTS |
| `DEEPGRAM_API_KEY` | secret | STT |
| `CLERK_SECRET_KEY` | secret | Clerk JWT verification |
| `CLERK_FRONTEND_API_URL` | variable | e.g. https://xxx.clerk.accounts.dev |
| `BODHI_ALLOWED_ORIGINS` | variable | your frontend origin, e.g. https://app.vercel.app |
| `PROCTORING_ENABLED` | variable | `false` (browser-side CV) |

`REDIS_URL` is preset to the in-container Redis.

On the Space, this file must be named `README.md` and the Dockerfile
`Dockerfile`.
