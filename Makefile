PY ?= python
PORT ?= 8020
VENV ?= .venv

.PHONY: help install run test bench docker clean

help:
	@echo "make install   create $(VENV) and install runtime + dev dependencies"
	@echo "make run       serve the API and dashboard on http://127.0.0.1:$(PORT)"
	@echo "make test      run the full suite (maths, API, BDD, tenancy)"
	@echo "make bench     benchmark the five-model comparison endpoint"
	@echo "make docker    build the container image"
	@echo "make clean     remove caches and the local SQLite database"

install:
	$(PY) -m venv $(VENV)
	$(VENV)/bin/python -m pip install --upgrade pip
	$(VENV)/bin/python -m pip install -r requirements-dev.txt

run:
	$(VENV)/bin/python -m uvicorn channeltruth.main:app --app-dir src --reload --port $(PORT)

test:
	$(VENV)/bin/python -m pytest -q

bench:
	LOG_LEVEL=CRITICAL PYTHONPATH=src $(VENV)/bin/python scripts/bench_compare.py

docker:
	docker build -t channeltruth:1.0.0 .

clean:
	rm -rf .pytest_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -f channeltruth.db
