# ── FlexClaw3 Dockerfile ──────────────────────────────────────────────────────
# Immagine multi-stage: build con uv, runtime snello con Playwright

# ── Stage 1: build delle dipendenze ──────────────────────────────────────────
FROM python:3.11-slim AS builder

# Installa uv per gestione pacchetti
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Copia solo i file di dipendenza per sfruttare la cache Docker
COPY pyproject.toml uv.lock ./

# Installa le dipendenze in un virtualenv locale
RUN uv venv .venv && uv sync --no-dev --frozen

# ── Stage 2: immagine di runtime ─────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Dipendenze di sistema per Playwright Chromium, librerie native e font emoji
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libatspi2.0-0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libwayland-client0 \
    fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copia uv e il virtualenv dal builder
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv
COPY --from=builder /app/.venv .venv

# Installa i browser Playwright nel runtime
RUN .venv/bin/python -m playwright install chromium

# Copia il codice sorgente del progetto
COPY main.py run_telegram.py ./
COPY core/ core/
COPY plugin/ plugin/
COPY config/ config/

# Crea le directory per dati persistenti
RUN mkdir -p data/db data/chromadb data/logs sandbox

# Variabili d'ambiente di default
ENV PYTHONUNBUFFERED=1
ENV APP_ENV=production
ENV AGENT_OS_PORT=7777

EXPOSE 7777

# Entry point: avvia FlexClaw (Telegram + API)
CMD [".venv/bin/python", "main.py"]
