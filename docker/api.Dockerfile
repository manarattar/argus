# ARGUS API image.
#
# Multi-stage so the runtime layer carries only the installed dependencies and
# the application, not the build toolchain.

FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt


FROM python:3.11-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="/app:/app/apps/api"

# Run as a non-root user.
RUN useradd --create-home --uid 10001 argus

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY ai ./ai
COPY apps/api ./apps/api
COPY scripts ./scripts
COPY data ./data
COPY pyproject.toml ./

RUN chown -R argus:argus /app
USER argus

EXPOSE 8000

# The application creates any missing tables on startup, so a fresh volume
# comes up working rather than erroring.
CMD ["uvicorn", "argus_api.main:app", "--app-dir", "apps/api", "--host", "0.0.0.0", "--port", "8000"]
