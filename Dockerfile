# ============================
# Builder stage
# ============================
FROM ghcr.io/astral-sh/uv:python3.13-alpine AS builder

# System build deps:
# - build-base: gcc, g++, musl-dev, etc.
# - linux-headers: provides <linux/ethtool.h> needed by psutil
# - python3-dev: Python headers for compiling C extensions
# - postgresql-dev: for psycopg2
RUN apk add --no-cache \
    build-base \
    linux-headers \
    python3-dev \
    postgresql-dev

WORKDIR /app

# Copy lockfiles first for better caching
COPY pyproject.toml uv.lock ./

# Create the venv and install deps exactly as locked
# (uv will compile wheels here inside /app/.venv)
RUN uv sync --frozen

# Copy the rest of the source after deps are installed
COPY . .

# Optional: run bytecode compilation to catch syntax errors early
# RUN uv run python -m compileall -q .


# ============================
# Runtime stage
# ============================
FROM ghcr.io/astral-sh/uv:python3.13-alpine AS runtime

# Runtime libs only (no compilers/headers)
RUN apk add --no-cache postgresql-libs

WORKDIR /app

# Copy just the virtualenv and your app code from builder
COPY --from=builder /app/.venv .venv
COPY --from=builder /app .

EXPOSE 8000

# Use uv to run Uvicorn with your FastAPI app
CMD ["uv", "run", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
