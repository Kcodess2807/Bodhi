FROM python:3.10-slim

# System deps for OpenCV, DeepFace, and MediaPipe
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libgl1 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first (layer cache)
COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt

# Copy application code
COPY src/ ./src/
COPY procturing_backend/ ./procturing_backend/

# Pre-download YOLO model so container startup is fast
# (downloads to /root/ultralytics on first import if not present)
ARG YOLO_MODEL=yolov8n.pt
ENV YOLO_MODEL_VARIANT=yolov8n

# Non-root user for security
RUN useradd -m -u 1000 bodhi && chown -R bodhi:bodhi /app
USER bodhi

EXPOSE 8000

# Single uvicorn worker — the app loads heavy CV models once at startup.
# Scale horizontally (multiple containers) rather than vertically (more workers).
CMD ["gunicorn", "src.api.app:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "1", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--keep-alive", "5", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
