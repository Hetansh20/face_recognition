# ─── Stage 1: Base Image ──────────────────────────────────────────────────────
FROM python:3.11-slim

# ─── System Dependencies ──────────────────────────────────────────────────────
# libgl1 + libglib2.0-0 are required by OpenCV (headless still needs them)
# libgomp1 is needed by InsightFace/ONNX for multi-threaded inference
# g++ is needed to compile InsightFace's Cython C++ extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# ─── Working Directory ───────────────────────────────────────────────────────
WORKDIR /app

# ─── Install Python Dependencies ─────────────────────────────────────────────
# Install CPU-only PyTorch FIRST to avoid downloading 2GB+ of CUDA libraries
RUN pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cpu

# Copy requirements and install the rest
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ─── Copy Application Code ───────────────────────────────────────────────────
COPY . .

# ─── Create directories ──────────────────────────────────────────────────────
RUN mkdir -p registered_faces attendance_reports

# ─── Expose Port ────────────────────────────────────────────────────────────
EXPOSE 8080

# ─── Start Command ───────────────────────────────────────────────────────────
CMD gunicorn app:app \
    --bind 0.0.0.0:${PORT:-8080} \
    --workers 1 \
    --threads 4 \
    --timeout 120 \
    --log-level info
