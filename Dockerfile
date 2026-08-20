FROM python:3.12-slim

LABEL org.opencontainers.image.title="github-fork-sync"
LABEL org.opencontainers.image.description="Sync GitHub forks with upstream, with diff preview"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml ./
COPY src/ src/

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["gfs", "web", "--port", "8000"]
