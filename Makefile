PYTHON ?= python3
COMPOSE = docker compose --env-file .env -f deploy/compose.yaml
.PHONY: configure up down seed test test-contract export-dataset load-test backup restore local
configure:
	$(PYTHON) tools/configure.py
up: configure
	$(COMPOSE) up -d --build
up-ml: configure
	$(COMPOSE) --profile ml up -d --build
up-telegram: configure
	$(COMPOSE) --profile telegram up -d --build
down:
	$(COMPOSE) down
seed:
	$(COMPOSE) exec api python -m backend.seed
export-dataset:
	$(COMPOSE) exec api python -m tools.export_dataset
test:
	$(PYTHON) -m pytest --cov=backend --cov-report=term-missing
test-contract:
	$(PYTHON) -m pytest tests/contract/ml --ml-url=$(ML_URL)
load-test:
	$(PYTHON) -m locust -f tests/load/locustfile.py --headless -u 20 -r 5 -t 30s --host=$(API_URL) --csv=data/load
backup:
	mkdir -p data/backups
	$(COMPOSE) exec -T postgres pg_dump -U moscollector -Fc moscollector > data/backups/backup.dump
restore:
	$(COMPOSE) exec -T postgres pg_restore -U moscollector -d moscollector --clean --if-exists < data/backups/backup.dump
local:
	$(PYTHON) -m uvicorn backend.api:app --host 127.0.0.1 --port 8000
