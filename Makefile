# ZeroCloudGravity Engine & Workstation Makefile (v1.1.0)
export PYTHONDONTWRITEBYTECODE := 1
export ZCG_NO_BROWSER := 1

PYTHON ?= python3
VENV_BIN ?= $(if $(wildcard .venv/bin/pytest),.venv/bin,)
PYTEST ?= $(if $(VENV_BIN),$(VENV_BIN)/pytest,pytest)
RUFF ?= $(if $(VENV_BIN),$(VENV_BIN)/ruff,ruff)
MYPY ?= $(if $(VENV_BIN),$(VENV_BIN)/mypy,mypy)
ZCG ?= $(if $(wildcard .venv/bin/zcg),.venv/bin/zcg,PYTHONPATH=src $(PYTHON) -c "import sys; from zcg.cli.dispatcher import main; sys.exit(main())")
ZCG_MCP ?= $(if $(wildcard .venv/bin/zcg-mcp),.venv/bin/zcg-mcp,PYTHONPATH=src $(PYTHON) -c "import sys; from zcg.mcp.server import main; sys.exit(main())")
RELEASE_VERSION ?= $(shell tr -d '[:space:]' < VERSION)

.PHONY: help setup-dev status diff horizon sync task complete consult mcp-test lint lint-arch lint-skills format typecheck test-unit test-unit-isolated test-imp test-e2e test verify stage-showcase

help:
	@echo "ZeroCloudGravity (v$(RELEASE_VERSION)) — Engine & Node Targets"
	@echo "  make setup-dev           Create local .venv and install dev tools"
	@echo "  make status              Inspect workspace governance, topology, and runtime status"
	@echo "  make diff                Compare workspace files against upstream templates"
	@echo "  make horizon             Inspect 1-hop upstream/downstream horizon and drift"
	@echo "  make sync                Synchronize templates and governance state"
	@echo "  make task TASK=<id>      Claim an active task in WORKTASK.md"
	@echo "  make complete TASK=<id>  Mark an active task completed in WORKTASK.md"
	@echo "  make consult LAYER=<id> QUERY=<q>  Query a mounted or sibling layer via rcap1"
	@echo "  make mcp-test            Run zcg-mcp 9/9/3 deterministic self-test"
	@echo "  make lint                Run ruff check & format check across src/, tests/, and hooks"
	@echo "  make lint-arch           Run AST Hexagonal Functional Core & 1:1:1 AAA boundary audit"
	@echo "  make lint-skills         Run < 50 ms static security audit across SKILL.md & configs"
	@echo "  make format              Format src/, tests/, and hooks with ruff"
	@echo "  make typecheck           Run mypy --strict on src/zcg/, tests/, and hooks"
	@echo "  make test-unit           Run 100%-coverage unit suite (tests/unit/)"
	@echo "  make test-unit-isolated  Verify 1:1 isolated 100% coverage per module"
	@echo "  make test-imp            Run implementation contract suite (tests/imp/)"
	@echo "  make test-e2e            Run end-to-end persona journeys (tests/e2e/)"
	@echo "  make test                Run Unit + Imp + E2E suites at 100% branch coverage"
	@echo "  make verify              Run full 8-stage ./scripts/verify-repo.sh gate"
	@echo "  make stage-showcase      Provision live [CAP-01..CAP-10] ASGI showcase (ARGS=--stop)"
	@OSS_CONTRIB="$(OSS_CONTRIB)" PYTHONPATH=src $(PYTHON) -c 'from pathlib import Path; from zcg.governance.oss_contrib import should_expose_oss_targets; should_expose_oss_targets(Path.cwd()) and print("\n".join(["  make oss-push-branch     Push active feat/* or fix/* branch to private dev-<repo> CI (dev-only)", "  make oss-promote-master  Fast-forward verified branch to private master, clean branch & sync", "  make oss-publish         Export tracker-free snapshot to public upstream (CREATE_PR=1 for PR flow)"]))'

setup-dev:
	@$(PYTHON) -m venv .venv
	@.venv/bin/pip install --upgrade pip -r requirements-dev.txt -e .

status:
	@$(ZCG) status .

diff:
	@$(ZCG) diff-project .

horizon:
	@$(ZCG) inspect-horizon .

sync:
	@$(ZCG) sync-layer .

task:
	@$(ZCG) start-task . --task "$(TASK)"

complete:
	@$(ZCG) complete-task . --task "$(TASK)" $(if $(SUMMARY),--summary "$(SUMMARY)",)

consult:
	@$(ZCG) consult-layer . --layer "$(LAYER)" --query "$(QUERY)"

mcp-test:
	@$(ZCG_MCP) --self-test

lint:
	@$(RUFF) check src tests antigravity/.gemini/config/scripts
	@$(RUFF) format --check src tests antigravity/.gemini/config/scripts

lint-arch:
	@$(ZCG) lint-arch .

lint-skills:
	@$(ZCG) lint-skills .

format:
	@$(RUFF) format src tests antigravity/.gemini/config/scripts

typecheck:
	@MYPYPATH=src $(MYPY) --strict src/zcg tests antigravity/.gemini/config/scripts

test-unit:
	@PYTHONPATH=src $(PYTEST) tests/unit --cov=src/zcg --cov-branch --cov-report=term-missing --cov-fail-under=100
	@rm -f .coverage

test-unit-isolated:
	@for mod in $$(find src/zcg -name "*.py" ! -name "__init__.py" | sort); do \
		rel=$${mod#src/zcg/}; \
		pkg=$$(dirname "$$rel"); \
		base=$$(basename "$$rel" .py); \
		tfile="tests/unit/zcg/$$pkg/test_$$base.py"; \
		dotted="zcg.$$(echo "$$pkg" | tr / .).$$base"; \
		PYTHONPATH=src $(PYTEST) -q "$$tfile" --cov="$$dotted" --cov-branch --cov-fail-under=100 >/dev/null || exit 1; \
	done
	@rm -f .coverage
	@echo "1:1 isolated unit coverage (stmts + branches = 100.00%) verified across all modules."

test-imp:
	@PYTHONPATH=src $(PYTEST) tests/imp

test-e2e:
	@PYTHONPATH=src $(PYTEST) tests/e2e

test:
	@PYTHONPATH=src $(PYTEST) tests/unit tests/imp tests/e2e --cov=src/zcg --cov-branch --cov-report=term-missing --cov-fail-under=100
	@rm -f .coverage

verify:
	@./scripts/verify-repo.sh

stage-showcase:
	@$(ZCG) stage-showcase $(ARGS)

-include mk/oss-contrib.mk
