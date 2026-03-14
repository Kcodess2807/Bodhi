#!/bin/bash

# Bodhi Platform Startup Script
# Starts the unified Bodhi + Proctoring API server

echo "=========================================="
echo "  Starting Bodhi Platform"
echo "=========================================="
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  Warning: .env file not found"
    echo "   Copying .env.example to .env..."
    cp .env.example .env
    echo "   Please edit .env with your API keys before continuing"
    echo ""
    read -p "Press Enter to continue or Ctrl+C to exit..."
fi

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    python -m venv .venv
    echo "✓ Virtual environment created"
    echo ""
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source .venv/bin/activate

# Install/update dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt --quiet
echo "✓ Dependencies installed"
echo ""

# Check for required API keys
echo "🔑 Checking configuration..."
source .env

if [ -z "$SARVAM_API_KEY" ] || [ "$SARVAM_API_KEY" = "your_sarvam_api_key_here" ]; then
    echo "⚠️  SARVAM_API_KEY not configured in .env"
fi

if [ -z "$GOOGLE_API_KEY" ] || [ "$GOOGLE_API_KEY" = "your_google_api_key_here" ]; then
    echo "⚠️  GOOGLE_API_KEY not configured in .env"
fi

if [ -z "$DATABASE_URL" ]; then
    echo "⚠️  DATABASE_URL not configured in .env (required for API server)"
fi

echo ""
echo "=========================================="
echo "  Starting Bodhi API Server"
echo "=========================================="
echo ""
echo "Features enabled:"
echo "  ✓ Voice Interview (STT/TTS/LLM)"
echo "  ✓ RAG Document System"
echo "  ✓ Proctoring (Face/Gaze/Object Detection)"
echo ""
echo "API Documentation:"
echo "  • Swagger UI: http://localhost:8000/docs"
echo "  • ReDoc:      http://localhost:8000/redoc"
echo ""
echo "Press Ctrl+C to stop the server"
echo ""

# Start the server
uvicorn src.api.app:app --reload --host 0.0.0.0 --port 8000
