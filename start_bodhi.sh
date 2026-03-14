#!/bin/bash
set -e

echo "=========================================="
echo "  Starting Bodhi Platform"
echo "=========================================="

# ── Environment setup ─────────────────────────────────────────────
if [ ! -f .env ]; then
    echo "Warning: .env not found, copying .env.example..."
    cp .env.example .env
    echo "Edit .env with your API keys, then re-run."
    exit 1
fi

# Use server-only requirements when running in production/no-audio mode
REQUIREMENTS="requirements-server.txt"
if [ "${BODHI_MODE}" = "cli" ]; then
    REQUIREMENTS="requirements.txt"
fi

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install -r "${REQUIREMENTS}" --quiet
echo "Dependencies ready."

# ── Config validation ──────────────────────────────────────────────
source .env 2>/dev/null || true

[ -z "$SARVAM_API_KEY" ]  && echo "WARNING: SARVAM_API_KEY not set"
[ -z "$GOOGLE_API_KEY" ]  && echo "WARNING: GOOGLE_API_KEY not set"
[ -z "$DATABASE_URL" ]    && echo "WARNING: DATABASE_URL not set (required)"

HOST="${BODHI_HOST:-0.0.0.0}"
PORT="${BODHI_PORT:-8000}"

# ── Launch ─────────────────────────────────────────────────────────
echo ""
echo "API docs: http://${HOST}:${PORT}/docs"
echo ""

if [ "${BODHI_ENV}" = "development" ]; then
    # Development: auto-reload on code changes
    uvicorn src.api.app:app --reload --host "${HOST}" --port "${PORT}"
else
    # Production: gunicorn with a single uvicorn worker
    # Scale by running multiple containers, not multiple workers —
    # each worker loads ~2 GB of CV models independently.
    exec gunicorn src.api.app:app \
        --worker-class uvicorn.workers.UvicornWorker \
        --workers 1 \
        --bind "${HOST}:${PORT}" \
        --timeout 120 \
        --keep-alive 5 \
        --access-logfile - \
        --error-logfile -
fi
