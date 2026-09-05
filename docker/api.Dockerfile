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
COPY pyproject.toml alembic.ini ./

COPY docker/entrypoint.sh /usr/local/bin/argus-entrypoint
# Strip carriage returns before making it executable. A checkout on Windows can
# carry CRLF, which turns the shebang into "/bin/sh<CR>" and fails at runtime
# with a bewildering "no such file or directory" naming a file that plainly
# exists. Normalising here makes the image independent of how the source
# arrived.
RUN sed -i 's/\r$//' /usr/local/bin/argus-entrypoint \
    && chmod +x /usr/local/bin/argus-entrypoint

RUN chown -R argus:argus /app
USER argus

EXPOSE 8000

# Migrate, seed if empty, then serve. See docker/entrypoint.sh.
CMD ["argus-entrypoint"]
