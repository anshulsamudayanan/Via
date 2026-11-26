# syntax=docker/dockerfile:1
# VIA API image (also used for the one-shot migration job).
# Build context: repository root.
# Optional build secret `build_ca`: extra CA bundle for TLS-intercepting proxies
# (set VIA_BUILD_CA_CERT for Compose). Never copied into an image layer.

FROM python:3.13.9-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN python -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
WORKDIR /src
# Locked third-party dependencies first, for layer caching.
COPY apps/api/requirements.lock ./requirements.lock
RUN --mount=type=secret,id=build_ca \
    if [ -s /run/secrets/build_ca ]; then export PIP_CERT=/run/secrets/build_ca; fi; \
    pip install --require-virtualenv -r requirements.lock
COPY services/pcb-engine ./services/pcb-engine
COPY services/ai-engine ./services/ai-engine
COPY services/optimization ./services/optimization
COPY apps/api ./apps/api
RUN --mount=type=secret,id=build_ca \
    if [ -s /run/secrets/build_ca ]; then export PIP_CERT=/run/secrets/build_ca; fi; \
    pip install --require-virtualenv --no-deps ./services/pcb-engine ./services/ai-engine ./services/optimization ./apps/api

FROM python:3.13.9-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH
RUN groupadd --system via && useradd --system --gid via --create-home --home-dir /home/via via
COPY --from=build /opt/venv /opt/venv
USER via
WORKDIR /home/via
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2)"]
CMD ["via-api", "serve", "--host", "0.0.0.0", "--port", "8000"]
