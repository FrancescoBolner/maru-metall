# Non-Docker workflow (macOS / Linux / WSL). Windows without make: scripts\start.ps1
SHELL := /bin/bash
PY ?= python3.12
VENV := .venv
BIN := $(VENV)/bin
PORT ?= 8000

.PHONY: help install build run dev test knowledge accuracy docker clean-data

help:
	@echo "make run       install, build the web app and start on http://localhost:$(PORT)"
	@echo "make dev       API with auto-reload on :8000 + Vite dev server on :5173"
	@echo "make test      backend tests"
	@echo "make knowledge rebuild drives/maru/knowledge/Maru_knowledge.xlsx from Maru's workbooks"
	@echo "make accuracy  compare the assistant with Maru's real offers"
	@echo "make docker    docker compose up --build"

$(BIN)/python:
	$(PY) -m venv $(VENV)

install: $(BIN)/python
	$(BIN)/python -m pip install -q -r backend/requirements-dev.txt
	cd frontend && npm ci --no-audit --no-fund

build:
	cd frontend && npm run build

run: install build
	$(BIN)/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port $(PORT)

dev: install
	trap 'kill 0' EXIT; \
	$(BIN)/python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload --reload-dir backend & \
	(cd frontend && npm run dev) & \
	wait

test:
	$(BIN)/python -m pytest backend/tests -q

knowledge:
	$(BIN)/python scripts/build_knowledge.py

accuracy:
	$(BIN)/python scripts/accuracy_check.py

docker:
	docker compose up --build

clean-data:
	rm -rf data/cache data/runs data/*.sqlite data/training/* logs/*.jsonl drives/maru/reports/*/
