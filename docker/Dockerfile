# ============ Build Stage ============
FROM python:3.12-slim-bookworm AS builder

RUN pip install uv

WORKDIR /app

# Enable bytecode compilation for faster startup
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

# Copy dependency files first (layer caching)
COPY pyproject.toml uv.lock* ./

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev 2>/dev/null || \
    uv sync --no-install-project --no-dev

# Copy source code
COPY src/ src/
COPY gunicorn.conf.py .
COPY alembic.ini .
COPY alembic/ alembic/

# Install the project itself
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev 2>/dev/null || \
    uv sync --no-dev

# ============ Runtime Stage ============
FROM python:3.12-slim-bookworm AS runtime

RUN groupadd -r app && useradd -r -g app app

WORKDIR /app

# Copy built virtual environment
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/gunicorn.conf.py /app/
COPY --from=builder /app/alembic.ini /app/
COPY --from=builder /app/alembic /app/alembic

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src

USER app

EXPOSE 8000

CMD ["gunicorn", "-c", "gunicorn.conf.py", "app.main:app"]
