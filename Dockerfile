# ABOUTME: Image for the frozen Tox21 FastAPI inference service (offline; no training, no data download).
# ABOUTME: Installs the exact research environment and serves tox21_research.api with the frozen model files.
FROM python:3.11-slim

ENV PYTHONPATH=/app/src \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# dependencies first (cacheable layer); requirements.txt pins the research venv including torch CPU source
COPY environment/requirements.txt ./environment/requirements.txt
RUN pip install --no-cache-dir -r environment/requirements.txt

# application code and frozen model artifacts only (no training data, no dataset cache)
RUN useradd --system --uid 10001 --create-home tox21
COPY --chown=tox21:tox21 src/ ./src/
COPY --chown=tox21:tox21 results/final/ ./results/final/

USER tox21

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

CMD ["uvicorn", "tox21_research.api:app", "--host", "0.0.0.0", "--port", "8000"]
