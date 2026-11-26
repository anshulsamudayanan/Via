# syntax=docker/dockerfile:1
# VIA EDA runner: KiCad's own tools (DRC) as an internal service.
# Based on the official KiCad image (GPL-3.0; KiCad runs as a separate program, VIA doesn't link it).
# Build context: repository root. No build-time network access is needed.
#
# The container holds no credentials: no database, storage or queue access. It only receives
# bundles from the worker over Compose's internal `eda` network and returns KiCad's report.
FROM kicad/kicad:9.0.6@sha256:3371f20b29f2fce4c0ee118fcf7f37a1237028321a5ada949512bc92781825d9
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/via-eda
COPY --chown=root:root services/eda-runner/src/via_eda /opt/via-eda/via_eda
USER kicad
WORKDIR /tmp
EXPOSE 8100
HEALTHCHECK --interval=15s --timeout=30s --start-period=30s --retries=5 \
  CMD ["python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8100/health', timeout=25)"]
CMD ["python3", "-m", "via_eda.server"]
