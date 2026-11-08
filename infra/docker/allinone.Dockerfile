# Single-container deployment for free hosts (Hugging Face Spaces / Render / Railway / Fly):
# API serves the built UI; GigSim, MCP servers (in-process MCP sessions) and the worker run
# inside the API process; SQLite persistence on a volume. The open profile calls a hosted
# open-model provider (Groq) because free hosts have no GPU; without a key it degrades to
# the deterministic offline profile.
FROM node:22-alpine AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json* ./
RUN npm ci || npm install
COPY apps/web ./
COPY apps/api/openapi.json /api/openapi.json
RUN npm run build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app PIP_NO_CACHE_DIR=1 \
    GIGSIM_URL=inprocess MCP_TRANSPORT=inprocess GIGSIM_ERROR_RATE=0.01 GIGSIM_SPEED=6 PORT=7860
WORKDIR /app
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install $(python -c "import tomllib;print(' '.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))")
COPY . .
COPY --from=web /web/dist ./apps/web/dist
RUN python -c "from rag.embeddings import get_embedder, get_reranker; get_embedder(); get_reranker()"
RUN useradd -m app && mkdir -p /app/data/processed && chown -R app /app
USER app
EXPOSE 7860
CMD ["sh", "-c", "uvicorn apps.api.main:app --host 0.0.0.0 --port ${PORT}"]