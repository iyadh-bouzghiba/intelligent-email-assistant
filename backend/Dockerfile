# ============================================================================
# PRODUCTION-GRADE DOCKERFILE
# Intelligent Email Assistant - Render-Safe Deployment
# ============================================================================
#
# BOOT CONTRACT: python -m backend.infrastructure.worker_entry
# NO sys.path HACKS | NO WORKDIR TRICKS | FAIL-FAST VALIDATION
#
# This Dockerfile enforces package-based execution and prevents import errors
# by installing the backend as a proper Python package.
# ============================================================================

# ===== BUILDER STAGE =====
# Compile dependencies in isolated environment to minimize final image size
FROM python:3.11-slim as builder

WORKDIR /build

# Install build dependencies for Python packages with C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first (Docker layer caching optimization)
COPY requirements.txt .

# Install dependencies to user directory (isolated from system Python)
RUN pip install --no-cache-dir --user -r requirements.txt

# ===== FINAL STAGE =====
# Minimal runtime image without build tools
FROM python:3.11-slim

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# Copy compiled dependencies from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy entire backend package
COPY --chown=appuser:appuser . .

# Install backend as editable package
# This makes 'from backend.xxx import yyy' work from anywhere
RUN pip install --no-cache-dir -e .

# Set PATH to include user-installed binaries
ENV PATH=/home/appuser/.local/bin:$PATH

# Python configuration
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Switch to non-root user
USER appuser

# Expose port (Render will override with $PORT env var)
EXPOSE 8000

# Health check using Python instead of curl (no extra dependencies)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import http.client; conn=http.client.HTTPConnection('localhost:'+str(__import__('os').getenv('PORT', '8000'))); conn.request('GET', '/health'); r=conn.getresponse(); exit(0 if r.status == 200 else 1)"

# ===== BOOT CONTRACT ENFORCEMENT =====
# CANONICAL ENTRYPOINT - DO NOT MODIFY
# This command:
# - Executes backend as a Python module (-m flag)
# - Automatically resolves 'from backend.xxx' imports
# - Triggers validate_startup() before serving requests
# - Respects $PORT environment variable from Render
# ============================================================================
CMD ["python", "-m", "backend.infrastructure.worker_entry"]
