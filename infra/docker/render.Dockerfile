# Lite single-container image for small free hosts (Render free: 512 MB RAM).
# No local embedding/reranker models: EMBED_PROVIDER=hash, RERANK_PROVIDER=lexical. Measured on the dev
# set, the shipped retrieval (BM25 + skill graph + multi-vector + outcome) scores the same in this mode
# (evals/results/rag_retrieval_lite.json vs rag_retrieval.json). LLM nodes call Groq (hosted open models).
FROM node:22-alpine AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json* ./
RUN npm ci || npm install
COPY apps/web ./
RUN npm run build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app PIP_NO_CACHE_DIR=1 \
    GIGSIM_URL=inprocess MCP_TRANSPORT=inprocess EMBED_PROVIDER=hash RERANK_PROVIDER=lexical \
    GIGSIM_ERROR_RATE=0.01 GIGSIM_SPEED=6 PORT=10000 MALLOC_ARENA_MAX=2
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install $(python -c "import tomllib;print(' '.join(d for d in tomllib.load(open('pyproject.toml','rb'))['project']['dependencies'] if not d.startswith(('fastembed','opentelemetry','langgraph-checkpoint-postgres','psycopg','arq','redis'))))")
COPY . .
COPY --from=web /web/dist ./apps/web/dist
RUN useradd -m app && mkdir -p /app/data/processed && chown -R app /app
USER app
EXPOSE 10000
CMD ["sh", "-c", "uvicorn apps.api.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]