# Listweavarr has no third-party Python runtime dependencies.
FROM python:3.14-slim
LABEL org.opencontainers.image.title="Listweavarr" \
      org.opencontainers.image.source="https://github.com/RayRayElite/Listweavarr" \
      org.opencontainers.image.licenses="AGPL-3.0-only"
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1 \
    LISTWEAVARR_HOST=0.0.0.0 LISTWEAVARR_PORT=8765 \
    LISTWEAVARR_DATA_DIR=/config LISTWEAVARR_OPEN_BROWSER=0
WORKDIR /app
COPY *.py VERSION LICENSE ./
COPY web/ ./web/
COPY catalogue/bundled/ ./catalogue/bundled/
RUN mkdir -p /config && chown 10001:10001 /config
USER 10001:10001
VOLUME ["/config"]
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.environ.get('LISTWEAVARR_PORT','8765')+'/healthz',timeout=3)" || exit 1
CMD ["python", "app.py"]
