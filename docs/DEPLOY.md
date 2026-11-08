# Deploying the public link

**Shipped host: Render (free).** Hugging Face now requires a PRO plan for Docker Spaces, so the free deployment uses Render with
`render.yaml` + `infra/docker/render.Dockerfile` (lite mode: no local embedding model). Measured on the dev set, the shipped
retrieval scores the same in lite mode (`evals/results/rag_retrieval_lite.json`: Recall@5 0.949 vs 0.949). Measured locally: peak memory
~200 MB (limit 512 MB); with `WORKER_CONCURRENCY=1` every Groq call succeeded (analyst 19/19, writer 10/10, critic 10/10) within the
free-tier rate limit.

## Render

1. render.com → sign in with GitHub → **New → Blueprint** → pick this repository → Render reads `render.yaml`.
2. When asked, paste the four secrets (`GROQ_API_KEY`, `SECRET_KEY`, `TOKEN_ENC_KEY`, `REVIEWER_PASSWORD`).
3. Wait for the build (~10 min). The URL is `https://gigbid-<suffix>.onrender.com`.
4. The free plan sleeps after 15 minutes idle; the first request wakes it (~1 min). Data lives on the instance's disk and resets on redeploy;
   the reviewer account is re-created automatically on start.

## Option A - Hugging Face Spaces (free, 16 GB RAM CPU)

1. Create a Space: Docker SDK, public, hardware "CPU basic".
2. Push this repo to the Space. Its README front-matter must contain `sdk: docker` and
   `app_port: 7860`, and a root `Dockerfile` that is a copy of `infra/docker/allinone.Dockerfile`:
   ```bash
   cp infra/docker/allinone.Dockerfile Dockerfile
   git remote add space https://huggingface.co/spaces/<you>/gigbid
   git push space main
   ```
3. Space → Settings → **Variables and secrets** (secrets, never in the repo):
   `GIGBID_PROFILE=open`, `GROQ_API_KEY`, `SECRET_KEY` (32+ random chars),
   `TOKEN_ENC_KEY` (Fernet key), `REVIEWER_EMAIL`, `REVIEWER_PASSWORD`,
   `REVIEWER_PERSONA=aiml`, `GIGBID_ENV=prod`, `COOKIE_SECURE=1`, `OLLAMA_SMALL_MODEL` (unused
   when Groq is set; the small-model nodes fall back to Groq `gpt-oss-20b` by setting
   `WRITER_PROVIDER=groq`).
4. Turn on persistent storage (or accept that demo data resets on restart).
5. The Space URL is your **deployed link**. Log in with the reviewer account and confirm
   that the inbox fills within a minute (GigSim's clock starts 12 simulated hours in).

## Option B - Render / Railway / Fly.io

Use the same Dockerfile and `PORT` env var, at least 2 GB RAM (embedding model + reranker),
and a volume mounted at `/app/data/processed`.

## Keep it live until grades are released

The hidden test run hits the live URL after the deadline, and a sleeping free instance
loses the E marks. Spaces stay up while public. On Render, use a paid instance or an uptime
pinger on `/api/health`.

## Full stack (Postgres, Redis, Phoenix, Ollama)

On a VM: `cp .env.example .env`, fill it in, then
`docker compose -f infra/docker-compose.yml up -d --build`. Expose `web` (8080) behind
HTTPS (Caddy or nginx), and expose Phoenix (6006) only if you want public trace links.
