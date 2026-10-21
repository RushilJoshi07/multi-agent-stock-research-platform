# Fathom developer commands (CLAUDE.md, "How to run").
# Node and uv are pinned versions installed from official release archives into ~/.local
# (docs/decisions/0003, 0007). Override the paths if yours differ.
NODE24_BIN ?= $(HOME)/.local/node/v24.21.0/bin
UV_BIN ?= $(HOME)/.local/uv/0.12.23
UV := $(UV_BIN)/uv
NPM := cd web && PATH="$(NODE24_BIN):$$PATH" npm

.PHONY: up down ps logs test test-web lint gate

# Start Postgres, Redis, the API and the web app; return once all four are healthy.
# --renew-anon-volumes: give web a fresh node_modules volume from the image, not the old one.
up:
	docker compose up -d --build --wait --renew-anon-volumes

# Stop and remove the containers. Never -v: deleting volumes deletes data (ask first).
down:
	docker compose down

ps:
	docker compose ps

logs:
	docker compose logs --tail=200

test:
	$(UV) run pytest

test-web:
	$(NPM) run test

lint:
	$(UV) run ruff check
	$(UV) run ruff format --check
	$(NPM) run lint
	$(NPM) run typecheck

# FATHOM_GATE=1 turns on the check in tests/gates/conftest.py that fails the run if any
# gate test was deselected or skipped, or none ran.
gate:
	@test -n "$(PHASE)" || { echo "usage: make gate PHASE=<n>"; exit 2; }
	FATHOM_GATE=1 $(UV) run pytest tests/gates/test_phase$(PHASE)_gate.py -m gate -v -rA
