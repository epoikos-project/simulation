FROM mcr.microsoft.com/devcontainers/python:3.13-bookworm
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN useradd -ms /bin/bash epoikos
USER epoikos
WORKDIR /workspace

# Copy and install dependencies
COPY pyproject.toml uv.lock ./

CMD ["bash", "-c", "tail -f /dev/null"]