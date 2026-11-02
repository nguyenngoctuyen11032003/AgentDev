# ==============================================================================
# AgentDev - all Python commands run inside backend/ (uv project lives there)
# ==============================================================================

BACKEND_DIR := backend
FRONTEND_DIR := frontend

# ==============================================================================
# Setup
# ==============================================================================

.PHONY: install
install: ## Install backend (uv) and frontend (npm) dependencies
	@cd $(BACKEND_DIR) && uv sync
	@cd $(FRONTEND_DIR) && npm install

# ==============================================================================
# Development Commands
# ==============================================================================

.PHONY: dev
dev: ## Run both backend and frontend development servers
	@$(MAKE) -j2 server client


.PHONY: server
server: ## Start the backend server in the background
	@echo "Starting server in background..."
	@cd $(BACKEND_DIR) && uv run python main.py --port 6400 &

.PHONY: client
client: ## Start the frontend development server
	@cd $(FRONTEND_DIR) && npx cross-env VITE_API_BASE_URL=http://localhost:6400 npm run dev

.PHONY: stop
stop: ## Stop backend and frontend servers cross-platform
	@echo "Stopping backend server (port 6400) and frontend server (port 5173)..."
	@npx --yes kill-port 6400 5173

# ==============================================================================
# Tools & Maintenance
# ==============================================================================

.PHONY: sync
sync: ## Sync Vue graphs to the server database
	@cd $(BACKEND_DIR) && uv run python -m scripts.sync_vuegraphs

.PHONY: validate-yamls
validate-yamls: ## Validate all YAML configuration files
	@cd $(BACKEND_DIR) && uv run python -m scripts.validate_all_yamls

# ==============================================================================
# Help
# ==============================================================================

.PHONY: help
help: ## Display this help message
	@uv run --no-project python -c "import re; \
	p=r'$(firstword $(MAKEFILE_LIST))'.strip(); \
	[print(f'{m[0]:<20} {m[1]}') for m in re.findall(r'^([a-zA-Z_-]+):.*?## (.*)$$', open(p, encoding='utf-8').read(), re.M)]" | sort

# ==============================================================================
# Quality Checks
# ==============================================================================

.PHONY: check-backend
check-backend: ## Run backend quality checks (tests + linting)
	@$(MAKE) backend-tests
	@$(MAKE) backend-lint

.PHONY: backend-tests
backend-tests: ## Run backend tests
	@cd $(BACKEND_DIR) && uv run pytest -v

.PHONY: backend-lint
backend-lint: ## Run backend linting
	@uvx ruff check $(BACKEND_DIR) workspace/functions

.PHONY: frontend-build
frontend-build: ## Build the frontend for production
	@cd $(FRONTEND_DIR) && npm run build

.PHONY: frontend-lint
frontend-lint: ## Run frontend linting (ESLint)
	@cd $(FRONTEND_DIR) && npm run lint
