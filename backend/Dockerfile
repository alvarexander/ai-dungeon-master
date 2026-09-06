# =====================================================================
# Dockerfile — the recipe for packaging this backend
# =====================================================================
#
# WHAT A CONTAINER IS
# A container is your application packaged together with everything it needs to
# run: the right Python version, the libraries, the system tools. The result
# behaves identically on your laptop and on Fly.io, which removes the entire
# category of problem that begins "but it works on my machine".
#
# WHY THE BACKEND NEEDS ONE AND THE FRONTEND DOES NOT
# The Angular app compiles to plain files that any web server hands over
# unchanged — there is no program to run, so there is nothing to package. This
# backend is a running Python program with two dozen dependencies, one of which
# needs audio libraries. That has to be packaged.
#
# WHY THERE ARE TWO "FROM" LINES BELOW
# This is a multi-stage build. The first stage installs the dependencies, which
# needs compilers and build tools. The second stage copies only the finished
# result into a clean image, leaving the build tools behind.
#
# The benefit is not only size. Every tool present in a running container is a
# tool available to an attacker who gets in. A production image with no
# compiler is a meaningfully smaller target.
# =====================================================================

# ---------------------------------------------------------------------
# Stage 1: build the dependencies
# ---------------------------------------------------------------------
FROM python:3.12-slim AS builder

# uv installs Python packages considerably faster than pip.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /build

# Copy ONLY the dependency files first, before the application code.
#
# Docker caches each step and reuses it while its inputs are unchanged. Because
# the application changes constantly and the dependency list rarely does, this
# ordering means a normal code change reuses the cached dependency install and
# rebuilds in seconds instead of minutes.
COPY pyproject.toml ./

# --extra voice installs the speech-to-text libraries, so that audio is
# transcribed on our own server rather than being sent to a third party.
# Removing it makes the image much smaller and disables voice input.
RUN uv venv /opt/venv \
    && VIRTUAL_ENV=/opt/venv uv pip install --no-cache -r pyproject.toml --extra voice

# ---------------------------------------------------------------------
# Stage 2: the image that actually runs
# ---------------------------------------------------------------------
FROM python:3.12-slim

# ffmpeg decodes the audio formats browsers produce (WebM/Opus, MP4).
# curl is used by the health check below.
# --no-install-recommends keeps out packages we did not ask for.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

# Run as an ordinary user rather than root.
#
# By default a container runs everything as root. If an attacker finds a way to
# execute code, running as root hands them the whole container. This costs
# nothing and removes that.
RUN useradd --create-home --shell /bin/bash app

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app
COPY --chown=app:app app/ ./app/
COPY --chown=app:app migrations/ ./migrations/
COPY --chown=app:app scripts/ ./scripts/

# Download the speech model at BUILD time, not on first use.
#
# Without this, the first player to press the microphone button waits for a
# 145 MB download. Baking it in makes the image larger and every request fast.
# The script exits successfully if the voice libraries are absent, so the image
# still builds without them.
RUN python scripts/cache_speech_model.py

# Give the cached model to the application user, or it cannot read it.
RUN chown -R app:app /root/.cache 2>/dev/null || true
RUN mkdir -p /home/app/.cache && chown -R app:app /home/app/.cache
ENV HF_HOME=/home/app/.cache

USER app

EXPOSE 8000

# Fly.io also health-checks from outside (see fly.toml). This one is for any
# other platform, and for running the image locally.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

# No --reload here. That is a development convenience which watches the
# filesystem and restarts; in production it wastes memory and would restart the
# server if anything ever wrote to the application directory.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
