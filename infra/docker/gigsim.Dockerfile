FROM python:3.11-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install $(python -c "import tomllib;print(' '.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))")
COPY agent ./agent
COPY rag ./rag
COPY common ./common
COPY mcp_servers ./mcp_servers
COPY data ./data
COPY gigsim ./gigsim
COPY evals/__init__.py evals/metrics.py ./evals/
EXPOSE 8100
HEALTHCHECK CMD curl -fs http://localhost:8100/health || exit 1
CMD ["uvicorn", "gigsim.app:app", "--host", "0.0.0.0", "--port", "8100"]
