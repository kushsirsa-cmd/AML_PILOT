# ---------------------------------------------------------------------------
# AML Copilot — single-container image (UI + API + SQLite, demo data auto-seeded)
# One public port ($PORT). Ideal for free tiers: Render, Railway, Fly.io, Azure
# Container Apps, AWS App Runner, Google Cloud Run.
#   docker build -t aml-copilot . && docker run -p 8080:8080 aml-copilot
# ---------------------------------------------------------------------------
FROM node:20-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
# The browser only ever talks to the Next server; Next proxies /api/* to the API inside the container.
ENV BACKEND_URL=http://127.0.0.1:8000 NEXT_TELEMETRY_DISABLED=1
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 \
    DATABASE_URL=sqlite:////data/aml.db SEED_ON_STARTUP=true SEED_SIZE=full LLM_ENABLED=true \
    PORT=8080 HOSTNAME=0.0.0.0
COPY --from=node:20-slim /usr/local/bin/node /usr/local/bin/node
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY --from=web /web/.next/standalone ./web
COPY --from=web /web/.next/static ./web/.next/static
COPY docker/start.sh /app/start.sh
RUN chmod +x /app/start.sh && mkdir -p /data
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD python -c "import urllib.request,os;urllib.request.urlopen('http://127.0.0.1:%s/api/health'%os.environ.get('PORT','8080'))" || exit 1
CMD ["/app/start.sh"]
