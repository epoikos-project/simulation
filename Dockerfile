# ============================
# Builder stage
# ============================
FROM ghcr.io/astral-sh/uv:python3.13-alpine AS builder

# Install build dependencies (needed to compile psycopg2)
RUN apk add --no-cache postgresql-dev

WORKDIR /app

# Copy dependency files first (better caching)
COPY pyproject.toml uv.lock ./

# Install dependencies into .venv
RUN uv sync --frozen

# Copy the rest of the source code
COPY . .

# ============================
# Runtime stage
# ============================
FROM ghcr.io/astral-sh/uv:python3.13-alpine AS runtime

# Only the runtime library (no compiler, no dev headers)
RUN apk add --no-cache postgresql-libs

WORKDIR /app

# Copy only the virtualenv and source code from builder
COPY --from=builder /app/.venv .venv
COPY --from=builder /app .

EXPOSE 8000

# Run FastAPI app with Uvicorn
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

