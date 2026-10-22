# House Agent (Afe) - Docker Configuration
# STACK-001: FastAPI backend + Rust native module (afe_native, built with PyO3/maturin)

# ============================================================================
# Stage 1 - build the Rust extension as a wheel
# ============================================================================
FROM python:3.12-slim AS rust-build

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Minimal Rust toolchain; the exact version is pinned by rust/rust-toolchain.toml
RUN curl -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
ENV PATH="/root/.cargo/bin:${PATH}"

RUN pip install --no-cache-dir maturin

WORKDIR /src
COPY rust/ rust/
RUN maturin build --release -m rust/crates/afe-py/Cargo.toml -o /wheels

# ============================================================================
# Stage 2 - runtime image for the FastAPI backend
# ============================================================================
FROM python:3.12-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Rust extension (same Python version as the build stage)
COPY --from=rust-build /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

# Application code
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Non-root user
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Health check (standard library only, so it works without extra packages)
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
