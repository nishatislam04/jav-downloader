.PHONY: help install web web-termux test

PYTHON ?= python3
VENV ?= .venv
PIP = $(VENV)/bin/pip
PY = $(VENV)/bin/python

help:
	@echo "Targets:"
	@echo "  make install     Create venv and install package"
	@echo "  make web         Run web UI on http://127.0.0.1:8765"
	@echo "  make web-termux  Run web UI for Android Termux (0.0.0.0:8765)"
	@echo "  make test        Run pytest"

install:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install -U pip
	$(PIP) install -r requirements.txt
	$(PIP) install -e .

web:
	$(PY) -m uav_downloader.web.server --host 127.0.0.1 --port 8765

web-termux:
	UAV_WEB_HOST=0.0.0.0 UAV_WEB_PORT=8765 $(PY) -m uav_downloader.web.server

test:
	$(PY) -m pytest tests/ -q
