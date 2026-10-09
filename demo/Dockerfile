# Maru Metall — Takeoff & Quoting Assistant (demo). One image: API + built web app on port 8000.

# ---------- 1. web app (React + Vite) ----------
FROM node:22.11.0-bookworm-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---------- 2. API (Python 3.12 + FastAPI) ----------
FROM python:3.12.7-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    MARU_DEMO_ROOT=/demo
# Pango/HarfBuzz for WeasyPrint (PDF reports)
RUN apt-get update \
 && apt-get install -y --no-install-recommends libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0 libfontconfig1 \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /demo
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY backend backend
COPY config config
COPY scripts scripts
COPY docs docs
COPY --from=web /web/dist frontend/dist
# drives/, data/ and logs/ are mounted from the host (see docker-compose.yml)
RUN mkdir -p drives data logs
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')"
CMD ["python", "-m", "uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
