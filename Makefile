SHELL := /bin/bash
PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip
PYTEST ?= .venv/bin/pytest
RUFF ?= .venv/bin/ruff
PYTHONPATH_ENV := PYTHONPATH=backend:.
TERRAFORM ?= terraform

.DEFAULT_GOAL := help

.PHONY: help venv install install-ml dataset train eval eval-strict export pipeline test lint format check dev dashboard build-dashboard demo up up-ml down logs ps tunnel tf-fmt tf-check clean

help:
	@echo "Orbit — common commands"
	@echo ""
	@echo "  make install           Create .venv and install backend/dev deps"
	@echo "  make install-ml        Add torch/transformers/FAISS (large)"
	@echo "  make dataset           Generate 1,500 utterances/intent -> ml/data/splits"
	@echo "  make train             Fine-tune the DistilBERT intent+entity model"
	@echo "  make eval              Evaluate and write ml/artifacts/evaluation"
	@echo "  make eval-strict       Same, failing below macro-F1 0.90"
	@echo "  make export            Export ONNX and verify Torch parity"
	@echo "  make pipeline          dataset -> train -> export -> eval"
	@echo "  make test              Run the backend test suite"
	@echo "  make lint              Ruff check"
	@echo "  make check             lint + tests + dashboard typecheck"
	@echo "  make dev               Run the API (inline queue) on :8000"
	@echo "  make dashboard         Run the Vite dashboard on :5173"
	@echo "  make demo              Send a signed demo webhook and print the reply"
	@echo "  make up                Docker Compose stack (rules/lexical mode)"
	@echo "  make up-ml             Compose stack with ML dependencies installed"
	@echo "  make tunnel            Compose + ngrok profile for Meta webhooks"
	@echo "  make tf-fmt            Format the AWS Terraform stack"
	@echo "  make tf-check          terraform init + validate the AWS stack"
	@echo ""

venv:
	@test -d .venv || python3.11 -m venv .venv

install: venv
	$(PIP) install --upgrade pip
	$(PIP) install -r backend/requirements-dev.txt
	@echo "Backend ready. Dashboard: cd dashboard && npm install"

install-ml: install
	$(PIP) install -r ml/requirements.txt
	$(PIP) install -r backend/requirements-ml.txt

dataset:
	$(PYTHON) ml/scripts/generate_dataset.py --per-intent 1500 --seed 42

train:
	PYTHONUNBUFFERED=1 $(PYTHON) ml/scripts/train_intent.py --epochs 5 --batch-size 32 --lr 2e-5

eval:
	$(PYTHON) ml/scripts/evaluate.py

eval-strict:
	$(PYTHON) ml/scripts/evaluate.py --fail-under 0.90

export:
	$(PYTHON) ml/scripts/export_onnx.py

pipeline: dataset train export eval

test:
	$(PYTHONPATH_ENV) $(PYTEST) backend/tests -q

lint:
	$(RUFF) check backend shared ml/scripts scripts

format:
	$(RUFF) format backend shared ml/scripts scripts

check: lint test
	cd dashboard && npm run typecheck

dev:
	cd backend && PYTHONPATH=.. ../.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dashboard:
	cd dashboard && npm run dev

demo:
	$(PYTHON) scripts/demo_webhook.py $(ARGS)

tf-fmt:
	cd deploy/aws && $(TERRAFORM) fmt -recursive

tf-check:
	cd deploy/aws && $(TERRAFORM) init -backend=false -input=false
	cd deploy/aws && $(TERRAFORM) validate

build-dashboard:
	cd dashboard && npm run build

up:
	docker compose up --build

up-ml:
	INSTALL_ML=true docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=120 api worker

ps:
	docker compose ps

tunnel:
	docker compose --profile tunnel up --build

clean:
	rm -rf .pytest_cache .ruff_cache backend/.pytest_cache
	find . -type d -name __pycache__ -not -path './.venv/*' -not -path './dashboard/node_modules/*' -exec rm -rf {} +
