.PHONY: help install install-web web-build web web-api web-dev web-termux test

PYTHON ?= python3
VENV ?= .venv
PIP = $(VENV)/bin/pip
PY = $(VENV)/bin/python
NPM = npm
FRONTEND = web/frontend
STATIC = src/uav_downloader/web/static

help:
	@echo "Targets:"
	@echo "  make install       Create venv and install Python package"
	@echo "  make install-web   Install frontend deps (npm)"
	@echo "  make web-build     Build Solid UI into $(STATIC)"
	@echo "  make web           Build UI (if needed) and run on :8765"
	@echo "  make web-api       Run Python API only on :8765"
	@echo "  make web-dev       Vite dev server on :5173 (run web-api separately)"
	@echo "  make web-termux    Run web UI for Android Termux (0.0.0.0:8765)"
	@echo "  make test          Run pytest"

install:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install -U pip
	$(PIP) install -r requirements.txt
	$(PIP) install -e .

install-web:
	cd $(FRONTEND) && $(NPM) install

web-build: install-web
	cd $(FRONTEND) && $(NPM) run build

web-api:
	$(PY) -m uav_downloader.web.server --host 127.0.0.1 --port 8765

web: web-build
	$(PY) -m uav_downloader.web.server --host 127.0.0.1 --port 8765

web-dev: install-web
	cd $(FRONTEND) && $(NPM) run dev

web-termux: web-build
	UAV_WEB_HOST=0.0.0.0 UAV_WEB_PORT=8765 $(PY) -m uav_downloader.web.server

test:
	$(PY) -m pytest tests/ -q
