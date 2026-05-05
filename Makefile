PYTHON ?= 3.13
CONFIG ?= ./alarm-button.toml

.PHONY: help sync run emulator smoke install uninstall

help:
	@echo "Targets:"
	@echo "  sync       - install deps with uv"
	@echo "  run        - run API locally (params from config)"
	@echo "  emulator   - run GPIO emulator (params from config)"
	@echo "  smoke      - ping and SSE smoke check"
	@echo "  install    - install service via ./alarm-button.sh install"
	@echo "  uninstall  - uninstall service via ./alarm-button.sh uninstall"

sync:
	uv python install $(PYTHON)
	uv venv --python $(PYTHON)
	uv sync

run:
	uv run --python $(PYTHON) python ./alarm-button-run.py api --config $(CONFIG)

emulator:
	uv run --python $(PYTHON) python ./alarm-button-run.py emulator --config $(CONFIG)

smoke:
	curl -s http://127.0.0.1:8000/api/ping
	curl -N --max-time 3 http://127.0.0.1:8000/api/alarm-button/v1/button/events || true

install:
	bash ./alarm-button.sh install

uninstall:
	bash ./alarm-button.sh uninstall
