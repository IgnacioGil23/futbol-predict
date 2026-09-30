# syntax=docker/dockerfile:1

# ---------- Etapa 1: datos --------------------------------------------------
# Descarga Football-Data.co.uk y calcula el Elo al construir la imagen: los datos
# no se versionan en el repo.
FROM python:3.11-slim AS data
WORKDIR /app
COPY requirements-api.txt requirements-build.txt ./
RUN pip install --no-cache-dir -r requirements-build.txt
COPY src/ src/
COPY configs/ configs/
RUN python -m src.data.download \
 && python -m src.data.load \
 && python -m src.serving.build_state

# ---------- Etapa 2: runtime ------------------------------------------------
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app
RUN useradd --create-home --uid 10001 app
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt
COPY src/ src/
COPY models/production/model.json models/production/model.json
COPY --from=data /app/data/processed/serving_matches.parquet data/processed/serving_matches.parquet
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
  CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.getenv(\"PORT\", \"8000\")}/health', timeout=4)"
# Render define la variable PORT; localmente se usa 8000.
CMD ["sh", "-c", "uvicorn src.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
