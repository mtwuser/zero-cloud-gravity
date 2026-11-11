# ZeroCloudGravity Engine & Workstation Makefile (v1.0.0)
export PYTHONDONTWRITEBYTECODE := 1
export ZCG_NO_BROWSER := 1

PYTHON ?= python3
VENV_BIN ?= $(if $(wildcard .venv/bin/pytest),.venv/bin,)
PYTEST ?= $(if $(VENV_BIN),$(VENV_BIN)/pytest,pytest)
RUFF ?= $(if $(VENV_BIN),$(VENV_BIN)/ruff,ruff)
MYPY ?= $(if $(VENV_BIN),$(VENV_BIN)/mypy,mypy)
ZCG ?= $(if $(wildcard .venv/bin/zcg),.venv/bin/zcg,PYTHONPATH=src $(PYTHON) -c "import sys; from zcg.cli.dispatcher import main; sys.exit(main())")
ZCG_MCP ?= $(if $(wildcard .venv/bin/zcg-mcp),.venv/bin/zcg-mcp,PYTHONPATH=src $(PYTHON) -c "import sys; from zcg.mcp.server import main; sys.exit(main())")
OSS_REMOTE_URL ?= git@github.com:mtwuser/zero-cloud-gravity.git
RELEASE_VERSION ?= $(shell tr -d '[:space:]' < VERSION)

.PHONY: help setup-dev status diff horizon sync task complete consult mcp-test lint lint-arch format typecheck test-unit test-unit-isolated test-imp test-e2e test verify publish-oss

help:
	@echo "ZeroCloudGravity (v1.0.0) — Engine & Node Targets"
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
	@echo "  make format              Format src/, tests/, and hooks with ruff"
	@echo "  make typecheck           Run mypy --strict on src/zcg/, tests/, and hooks"
	@echo "  make test-unit           Run 100%-coverage unit suite (tests/unit/)"
	@echo "  make test-unit-isolated  Verify 1:1 isolated 100% coverage per module"
	@echo "  make test-imp            Run implementation contract suite (tests/imp/)"
	@echo "  make test-e2e            Run end-to-end persona journeys (tests/e2e/)"
	@echo "  make test                Run Unit + Imp + E2E suites at 100% branch coverage"
	@echo "  make verify              Run full 8-stage ./scripts/verify-repo.sh gate"
	@echo "  make publish-oss         Export tracker-free release snapshot to public upstream"

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

publish-oss: verify
	@test -z "$$(git status --porcelain)" || { echo "Error: working tree is dirty" >&2; exit 1; }
	@VER="$$(tr -d '[:space:]' < VERSION)" && test "$(RELEASE_VERSION)" = "$$VER" || { echo "Error: [OSS_PUBLISH_GUARD_BLOCKED] RELEASE_VERSION ($(RELEASE_VERSION)) must match VERSION ($$VER)" >&2; exit 1; }
	@! grep -q "^## \[Unreleased\]" CHANGELOG.md || { echo "Error: [OSS_UNRELEASED_CHANGELOG_BLOCKED] CHANGELOG.md still has [Unreleased]" >&2; exit 1; }
	@$(PYTHON) -c 'import json,sys; sys.exit(0 if json.load(open("system/zcg-node.json")).get("entity_kind")=="open-source" else 1)' || { echo "Error: [OSS_PERSONAL_REPO_PUBLISH_BLOCKED] entity_kind must be open-source" >&2; exit 1; }
	@$(ZCG) check-authority . --op release >/dev/null || { echo "Error: [UNAUTHORIZED_OSS_RELEASE] caller lacks release authority" >&2; exit 1; }
	@test -z "$$(git ls-remote --tags "$(OSS_REMOTE_URL)" "refs/tags/v$(RELEASE_VERSION)")" || { echo "Error: [OSS_TAG_ALREADY_PUBLISHED] tag v$(RELEASE_VERSION) already exists on $(OSS_REMOTE_URL)" >&2; exit 1; }
	@TMP_DIR="$$(mktemp -d)" && trap 'rm -rf "$$TMP_DIR"' EXIT && \
		if [ -z "$$(git ls-remote --tags "$(OSS_REMOTE_URL)" "refs/tags/v1.0.0")" ]; then \
			ORPHAN_ROOT=1; \
			mkdir -p "$$TMP_DIR/pub" && \
			git -C "$$TMP_DIR/pub" init --quiet -b master && \
			git -C "$$TMP_DIR/pub" remote add origin "$(OSS_REMOTE_URL)"; \
		else \
			ORPHAN_ROOT=0; \
			git clone --quiet "$(OSS_REMOTE_URL)" "$$TMP_DIR/pub" && \
			find "$$TMP_DIR/pub" -mindepth 1 -maxdepth 1 ! -name ".git" -exec rm -rf {} +; \
		fi && \
		git archive HEAD | tar -x -C "$$TMP_DIR/pub" && \
		rm -rf "$$TMP_DIR/pub"/WORK*.md "$$TMP_DIR/pub/BACKLOG.md" "$$TMP_DIR/pub/roadmaps" && \
		cd "$$TMP_DIR/pub" && git add -A && \
		if ! git diff --cached --quiet; then \
			git commit --quiet -m "chore(release): publish ZeroCloudGravity v$(RELEASE_VERSION)"; \
		fi && \
		git tag -f -a "v$(RELEASE_VERSION)" -m "Release v$(RELEASE_VERSION)" && \
		if [ "$(DRY_RUN)" = "1" ]; then \
			echo "[publish-oss DRY_RUN=1] Prepared v$(RELEASE_VERSION) (orphan_root=$$ORPHAN_ROOT, commits=$$(git rev-list --count HEAD)) for $(OSS_REMOTE_URL)"; \
		elif [ "$$ORPHAN_ROOT" = "1" ]; then \
			git push --force origin master --tags; \
		else \
			git push origin master --follow-tags; \
		fi
	@if [ "$(DRY_RUN)" != "1" ]; then ./scripts/workstation-sync.sh --sync --no-browser; fi
