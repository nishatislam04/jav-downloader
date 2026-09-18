.PHONY: help install install-web web-build web-build-if-needed start web web-api web-dev web-termux test

PYTHON ?= python3
VENV ?= .venv
PIP = $(VENV)/bin/pip
PY = $(VENV)/bin/python
NPM = npm
FRONTEND = web/frontend
STATIC = src/uav_downloader/web/static
WEB_PORT ?= 8765

# Termux sets TERMUX_VERSION; bind 0.0.0.0 and default to phone Downloads.
ifdef TERMUX_VERSION
WEB_HOST ?= 0.0.0.0
export DOWNLOAD_DIR ?= $(HOME)/storage/downloads
else
WEB_HOST ?= 127.0.0.1
endif

help:
	@echo "Targets:"
	@echo "  make install       Create venv and install Python package"
	@echo "  make install-web   Install frontend deps (npm)"
	@echo "  make web-build     Force-build Solid UI into $(STATIC)"
	@echo "  make start         Run web app (auto-build UI when npm is available)"
	@echo "  make web-api       Run Python API only on :$(WEB_PORT)"
	@echo "  make web-dev       Vite dev server on :5173 (run web-api separately)"
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

# Rebuild only when npm exists and sources are newer than the shipped bundle.
# Termux (no npm): skip build and use committed assets in $(STATIC).
web-build-if-needed:
	@if [ ! -f "$(STATIC)/index.html" ]; then \
		echo ">> No built UI found — building..."; \
		$(MAKE) web-build; \
	elif command -v $(NPM) >/dev/null 2>&1; then \
		if find "$(FRONTEND)/src" "$(FRONTEND)/index.html" -newer "$(STATIC)/index.html" 2>/dev/null | grep -q .; then \
			echo ">> Frontend sources changed — rebuilding..."; \
			$(MAKE) web-build; \
		else \
			echo ">> Using built UI ($(STATIC))"; \
		fi; \
	else \
		echo ">> npm not installed — using pre-built UI ($(STATIC))"; \
	fi

start: web-build-if-needed
	@[ -n "$(DOWNLOAD_DIR)" ] && mkdir -p "$(DOWNLOAD_DIR)" || true
	$(PY) -m uav_downloader.web.server --host "$(WEB_HOST)" --port "$(WEB_PORT)"

web: start
	@:

web-api:
	$(PY) -m uav_downloader.web.server --host "$(WEB_HOST)" --port "$(WEB_PORT)"

web-dev: install-web
	cd $(FRONTEND) && $(NPM) run dev

web-termux: start
	@:

test:
	$(PY) -m pytest tests/ -q
