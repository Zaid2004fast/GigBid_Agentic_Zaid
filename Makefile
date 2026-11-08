# GigBid tasks. On Windows without make, use:  python scripts/run.py <target>
PY ?= python
export PYTHONPATH := $(CURDIR)

.PHONY: dev test eval seed demo lint e2e smoke results zip up down

dev:      ## API + in-process worker/GigSim/MCP on :8000 and the web dev server on :5173
	$(PY) scripts/run.py dev
test:     ## unit + MCP + contract + integration tests
	$(PY) scripts/run.py test
eval:     ## retrieval, decision, GigSim reply-rate evaluations -> evals/results/*.json
	$(PY) scripts/run.py eval
smoke:    ## 30-job smoke eval with CI thresholds
	$(PY) scripts/run.py smoke
seed:     ## regenerate the synthetic world (personas, GigSim seed, dev set)
	$(PY) scripts/run.py seed
demo:     ## end-to-end demo: scout, analyse, approve, client reply (prints trace ids)
	$(PY) scripts/run.py demo
lint:     ## ruff + repository rules (secrets, gigsim frozen, prompts, README numbers)
	$(PY) scripts/run.py lint
e2e:      ## Playwright UI tests against a running API on :8000
	$(PY) scripts/run.py e2e
results:  ## regenerate the README results tables from evals/results
	$(PY) scripts/run.py results
zip:      ## build the submission ZIP (no .venv, node_modules, .env, models)
	$(PY) scripts/run.py zip
up:       ## docker compose up (everything)
	docker compose -f infra/docker-compose.yml up --build
down:
	docker compose -f infra/docker-compose.yml down