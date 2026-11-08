# Deploying the public link

The deployed link must work on the **open** profile, and free hosts have no GPU. The
single-container image (`infra/docker/allinone.Dockerfile`) therefore runs API + UI +
worker + GigSim + MCP servers in one process with SQLite, and calls a hosted open-model
provider (Groq: `openai/gpt-oss-120b` / `gpt-oss-20b`). Embeddings and the reranker run
on CPU inside the container. Without a `GROQ_API_KEY` it still works, falling back to the
deterministic offline path.

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
