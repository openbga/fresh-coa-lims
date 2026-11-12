# OpenBGA Fresh CoA LIMS application image. Base images are pinned by tag and digest; Dependabot
# proposes updates to both.
FROM ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 AS uv

# Build stage: install locked dependencies with the image's own Python and collect static
# assets. uv and its cache stay out of the runtime image.
FROM python:3.15.0-slim-trixie@sha256:f5b92f2a669a4c347044f29367f31983280b648250ca94dea66f98c53bc87e58 AS build
ENV UV_COMPILE_BYTECODE=1 UV_NO_CACHE=1 UV_PYTHON=/usr/local/bin/python3 UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY --from=uv /uv /bin/uv
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY . .
RUN DEBUG=true .venv/bin/python manage.py collectstatic --noinput \
    && chmod -R a+rX,go-w /app

# Runtime stage: application files are owned by root and read-only for the unprivileged
# runtime user, whose home directory and ~/.ssh remain writable for an operator shell.
FROM python:3.15.0-slim-trixie@sha256:f5b92f2a669a4c347044f29367f31983280b648250ca94dea66f98c53bc87e58
LABEL org.opencontainers.image.title="OpenBGA Fresh CoA LIMS" \
      org.opencontainers.image.description="Quality-control laboratory information management system for manufacturing (Django, PostgreSQL)" \
      org.opencontainers.image.source="https://github.com/openbga/fresh-coa-lims" \
      org.opencontainers.image.licenses="AGPL-3.0-only"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --create-home --shell /bin/bash app \
    && install -d -m 0700 -o app -g app /home/app/.ssh
WORKDIR /app
COPY --from=build /app /app
USER app
ENV HOME="/home/app" PATH="/app/.venv/bin:$PATH"
CMD ["sh", "-c", "exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --timeout 60 --error-logfile -"]
