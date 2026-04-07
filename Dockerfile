# ─── Stage 1: Base Image ──────────────────────────────────────────────────────
# Using Python 3.11 slim for minimal size. Also includes built-in native libs
# needed for OpenCV and InsightFace ONNX Runtime.
FROM python:3.11-slim

# ─── System Dependencies ────────────────────────────────────────────────────── 
# libgl1 + libglib2.0-0 are required by OpenCV (headless still needs them)
# libgomp1 is needed by InsightFace/ONNX for multi-threaded inference
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# ─── Working Directory ───────────────────────────────────────────────────────
WORKDIR /app

# ─── Install Python Dependencies ─────────────────────────────────────────────
# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ─── Copy Application Code ───────────────────────────────────────────────────
COPY . .

# ─── Create directories ──────────────────────────────────────────────────────
RUN mkdir -p registered_faces attendance_reports

# ─── Expose Port ────────────────────────────────────────────────────────────
# Railway injects $PORT dynamically; Gunicorn will bind to it.
EXPOSE 8080

# ─── Start Command ───────────────────────────────────────────────────────────
# - Using gunicorn (production WSGI) instead of Flask dev server.
# - --timeout 120 is important because InsightFace model loads can be slow.
# - 1 worker required because the face engine is a global stateful Python object.
CMD gunicorn app:app \
    --bind 0.0.0.0:${PORT:-8080} \
    --workers 1 \
    --threads 4 \
    --timeout 120 \
    --log-level info
