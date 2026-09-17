.PHONY: check fmt-check audit-backend audit-frontend trivy-iac \
        fmt validate lint-backend lint-backend-v2 lint-backend-v3 lint-frontend \
        test-backend build-frontend smoke-test clean

PYTHON  := backend/.venv/bin/python
PIP     := backend/.venv/bin/pip
PYTEST  := backend/.venv/bin/pytest
RUFF    := backend/.venv/bin/ruff
MYPY    := backend/.venv/bin/mypy

# ── Primary CI gate ────────────────────────────────────────────────────────────
# Mirrors what GitHub Actions runs locally — run before every push.
check: fmt-check lint-backend lint-backend-v2 lint-backend-v3 test-backend audit-backend \
       trivy-iac trivy-iac-phase2 trivy-iac-phase3 lint-frontend build-frontend audit-frontend

# ── Format check (read-only — does not modify files) ─────────────────────────
fmt-check:
	@echo ">>> Checking Terraform formatting (phase1)..."
	terraform -chdir=terraform/phase1 fmt -check -recursive
	@echo ">>> Checking Terraform formatting (phase2)..."
	terraform -chdir=terraform/phase2 fmt -check -recursive
	@echo ">>> Checking Terraform formatting (phase3)..."
	terraform -chdir=terraform/phase3 fmt -check -recursive
	@echo ">>> Checking Python formatting..."
	$(RUFF) format --check backend/

# ── Dependency audits ──────────────────────────────────────────────────────────
audit-backend:
	@echo ">>> Auditing Python dependencies..."
	pip-audit -r backend/requirements.txt --desc

audit-frontend:
	@echo ">>> Auditing Node dependencies..."
	cd frontend && npm audit --audit-level=high --omit=dev

# ── Trivy IaC scans ───────────────────────────────────────────────────────────
trivy-iac:
	@echo ">>> Running Trivy IaC scan on terraform/phase1/..."
	trivy config terraform/phase1/ \
		--severity HIGH,CRITICAL \
		--exit-code 1

trivy-iac-phase2:
	@echo ">>> Running Trivy IaC scan on terraform/phase2/..."
	trivy config terraform/phase2/ \
		--severity HIGH,CRITICAL \
		--exit-code 1 \
		--ignorefile terraform/phase2/.trivyignore

trivy-iac-phase3:
	@echo ">>> Running Trivy IaC scan on terraform/phase3/..."
	trivy config terraform/phase3/ \
		--severity HIGH,CRITICAL \
		--exit-code 1 \
		--ignorefile terraform/phase3/.trivyignore

# ── Terraform helpers ─────────────────────────────────────────────────────────
fmt:
	@echo ">>> Formatting Terraform (phase1 + phase2 + phase3)..."
	terraform -chdir=terraform/phase1 fmt -recursive
	terraform -chdir=terraform/phase2 fmt -recursive
	terraform -chdir=terraform/phase3 fmt -recursive

validate:
	@echo ">>> Validating Terraform (phase1)..."
	terraform -chdir=terraform/phase1 validate

# ── Linting ───────────────────────────────────────────────────────────────────
lint-backend:
	@echo ">>> Linting Phase 1 Python..."
	$(RUFF) check backend/app/ backend/tests/
	$(MYPY) backend/app/

lint-backend-v2:
	@echo ">>> Linting Phase 2 Python..."
	$(RUFF) check backend/v2/
	$(MYPY) backend/v2/

lint-backend-v3:
	@echo ">>> Linting Phase 3 Python..."
	$(RUFF) check backend/v3/ backend/webhooks/
	$(MYPY) backend/v3/ backend/webhooks/

lint-frontend:
	@echo ">>> Linting frontend..."
	cd frontend && npm run lint

# ── Tests ─────────────────────────────────────────────────────────────────────
test-backend:
	@echo ">>> Running backend unit tests..."
	cd backend && ../${PYTEST} tests/ -v --cov=app --cov=v2 --cov=v3 --cov=webhooks --cov-report=term-missing --cov-fail-under=80

# ── Frontend build ────────────────────────────────────────────────────────────
build-frontend:
	@echo ">>> Building frontend..."
	cd frontend && npm ci && npm run build

# ── Post-deploy smoke test ────────────────────────────────────────────────────
# Hits the live API endpoints to verify end-to-end health after a deploy.
# Default: prod URL.  Override: make smoke-test API_BASE_URL=https://dev-img.craftingnewtech.com
smoke-test:
	@echo ">>> Running smoke test against $${API_BASE_URL:-https://img.craftingnewtech.com}..."
	@API_BASE_URL=$${API_BASE_URL:-https://img.craftingnewtech.com} bash scripts/smoke-test.sh

# ── Clean ─────────────────────────────────────────────────────────────────────
clean:
	@echo ">>> Cleaning build artifacts..."
	rm -rf frontend/dist frontend/node_modules
	rm -rf backend/.venv backend/__pycache__ backend/.pytest_cache backend/.mypy_cache
	find . -name "*.zip" -not -path "./.git/*" -delete
	find . -name "__pycache__" -not -path "./.git/*" -exec rm -rf {} + 2>/dev/null || true
