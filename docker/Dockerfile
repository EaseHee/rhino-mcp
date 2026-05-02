# syntax=docker/dockerfile:1.6

FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy \
    UV_NO_PROGRESS=1

RUN apt-get update \
    && apt-get install --no-install-recommends -y curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast resolver) for reproducible builds.
ADD https://astral.sh/uv/install.sh /tmp/uv-install.sh
RUN sh /tmp/uv-install.sh && mv /root/.local/bin/uv /usr/local/bin/uv && rm /tmp/uv-install.sh

WORKDIR /app

# Copy lockable metadata first to leverage build-cache.
COPY pyproject.toml README.md /app/
COPY src /app/src

RUN uv pip install --system .

ENV RHINO_MCP_TRANSPORT=http \
    RHINO_MCP_LOG_LEVEL=INFO

EXPOSE 8765

ENTRYPOINT ["rhino-mcp"]
CMD ["--transport", "http", "--host", "0.0.0.0", "--port", "8765"]
