# ==============================================================================
# ARO — Multi-stage Production Dockerfile
# ==============================================================================
# Stage 1: Python base with dependencies
# Stage 2: Node.js for UI build
# Stage 3: Final slim image
# ==============================================================================

# ── Stage 1: Python dependencies ────────────────────────────────────────────
FROM python:3.12-slim AS base
WORKDIR /app

# Install system deps for chromadb (needs build tools for hnswlib)
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc g++ curl && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 2: Node.js UI build ──────────────────────────────────────────────
FROM node:20-alpine AS ui-builder
WORKDIR /ui
COPY ui/package*.json ./
RUN npm ci --production=false
COPY ui/ ./
RUN npm run build

# ── Stage 3: Final image ──────────────────────────────────────────────────
FROM base AS final
WORKDIR /app

# Copy application code
COPY . .

# Copy built UI from stage 2
COPY --from=ui-builder /ui/dist /app/ui/dist

# Create necessary directories
RUN mkdir -p /app/logs /app/vector_store

# Expose port
EXPOSE 5000

# Health check for orchestration platforms
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

# Production server: Gunicorn with gthread workers
# - 4 workers for multi-core utilization
# - 4 threads per worker for I/O concurrency
# - 300s timeout for long research sessions
CMD ["gunicorn", \
     "-w", "4", \
     "-k", "gthread", \
     "--threads", "4", \
     "--bind", "0.0.0.0:5000", \
     "--timeout", "300", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "app:app"]
