.PHONY: up down logs smoke test ui dev snapshot
up:
	docker compose up --build -d
down:
	docker compose down
logs:
	docker compose logs -f app seed
smoke:
	docker compose up --build -d
	python3 ops/smoke.py
test:
	uv run pytest --json-report --json-report-file=evals/results/pytest.json
ui:
	cd ui && npm ci && npm run build
dev:
	uv run uvicorn server.app:app --host 127.0.0.1 --port 8000
snapshot:
	uv run python -m seed.snapshot
