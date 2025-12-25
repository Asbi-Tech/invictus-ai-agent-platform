# Phase 0: Repository Scaffolding & CI Foundation

## Objectives

- Establish the complete folder structure for the monorepo
- Set up dependency management with split requirements files
- Configure development tooling (linting, type checking, testing)
- Create CI/CD workflow for automated quality checks
- Prepare environment configuration templates

## Prerequisites

- Git repository initialized (already done)
- Python 3.11+ available locally
- Access to Azure portal for configuration

## Implementation Tasks

### Task 0.1: Create Folder Structure

Create the following directory structure:

```
invictus-ai-agent-platform/
├── .github/
│   └── workflows/
│       └── ci.yml
├── requirements/
│   ├── base.txt
│   ├── dev.txt
│   ├── agent_api.txt
│   ├── mcp_common.txt
│   ├── mcp_opportunities.txt
│   ├── mcp_clients.txt
│   ├── mcp_risk_planning.txt
│   ├── mcp_admin_policy.txt
│   └── mcp_reporting.txt
├── apps/
│   ├── agent_api/
│   │   ├── src/
│   │   │   └── agent_api/
│   │   │       ├── __init__.py
│   │   │       ├── main.py
│   │   │       ├── api/
│   │   │       │   ├── __init__.py
│   │   │       │   ├── routes.py
│   │   │       │   └── schemas.py
│   │   │       ├── auth/
│   │   │       │   └── __init__.py
│   │   │       ├── streaming/
│   │   │       │   └── __init__.py
│   │   │       └── observability/
│   │   │           └── __init__.py
│   │   ├── tests/
│   │   │   └── __init__.py
│   │   └── requirements.txt
│   └── mcp_servers/
│       ├── opportunities/
│       │   ├── src/
│       │   │   └── mcp_opportunities/
│       │   │       ├── __init__.py
│       │   │       ├── server.py
│       │   │       ├── tools.py
│       │   │       ├── db.py
│       │   │       └── schemas.py
│       │   ├── tests/
│       │   │   └── __init__.py
│       │   └── requirements.txt
│       ├── clients/
│       │   ├── src/
│       │   │   └── mcp_clients/
│       │   │       └── __init__.py
│       │   ├── tests/
│       │   │   └── __init__.py
│       │   └── requirements.txt
│       ├── risk_planning/
│       │   ├── src/
│       │   │   └── mcp_risk_planning/
│       │   │       └── __init__.py
│       │   ├── tests/
│       │   │   └── __init__.py
│       │   └── requirements.txt
│       ├── admin_policy/
│       │   ├── src/
│       │   │   └── mcp_admin_policy/
│       │   │       └── __init__.py
│       │   ├── tests/
│       │   │   └── __init__.py
│       │   └── requirements.txt
│       └── reporting/
│           ├── src/
│           │   └── mcp_reporting/
│           │       └── __init__.py
│           ├── tests/
│           │   └── __init__.py
│           └── requirements.txt
├── packages/
│   ├── agent_core/
│   │   ├── src/
│   │   │   └── agent_core/
│   │   │       ├── __init__.py
│   │   │       ├── graph/
│   │   │       │   ├── __init__.py
│   │   │       │   ├── base_graph.py
│   │   │       │   ├── nodes/
│   │   │       │   │   └── __init__.py
│   │   │       │   └── subgraphs/
│   │   │       │       └── __init__.py
│   │   │       ├── state/
│   │   │       │   ├── __init__.py
│   │   │       │   └── models.py
│   │   │       ├── tools/
│   │   │       │   ├── __init__.py
│   │   │       │   ├── rag_gateway.py
│   │   │       │   ├── tavily_search.py
│   │   │       │   └── mcp_client.py
│   │   │       ├── policy/
│   │   │       │   ├── __init__.py
│   │   │       │   ├── tool_policy.py
│   │   │       │   └── tenant_policy.py
│   │   │       ├── memory/
│   │   │       │   ├── __init__.py
│   │   │       │   ├── cosmos_checkpointer.py
│   │   │       │   └── summarizer.py
│   │   │       └── eval/
│   │   │           ├── __init__.py
│   │   │           └── golden_tests.py
│   │   ├── tests/
│   │   │   └── __init__.py
│   │   └── pyproject.toml
│   ├── mcp_common/
│   │   ├── src/
│   │   │   └── mcp_common/
│   │   │       ├── __init__.py
│   │   │       ├── auth.py
│   │   │       ├── models/
│   │   │       │   └── __init__.py
│   │   │       └── telemetry.py
│   │   ├── tests/
│   │   │   └── __init__.py
│   │   └── pyproject.toml
│   └── common/
│       ├── src/
│       │   └── common/
│       │       ├── __init__.py
│       │       ├── config.py
│       │       ├── logging.py
│       │       └── errors.py
│       ├── tests/
│       │   └── __init__.py
│       └── pyproject.toml
├── infra/
│   └── bicep/
│       ├── main.bicep
│       ├── modules/
│       │   ├── container-apps.bicep
│       │   ├── cosmos-db.bicep
│       │   ├── key-vault.bicep
│       │   └── app-insights.bicep
│       └── parameters/
│           ├── dev.bicepparam
│           └── prod.bicepparam
├── docs/
│   ├── architecture.md
│   ├── tool-catalog.md
│   ├── streaming-events.md
│   ├── security.md
│   └── runbooks.md
├── scripts/
│   ├── local_dev.sh
│   └── seed_dev_data.py
├── plans/
│   └── (phase plans go here)
├── .env.example
├── .gitignore
├── pyproject.toml
└── README.md
```

### Task 0.2: Create Requirements Files

**requirements/base.txt**
```
pydantic>=2.9.0
python-dotenv>=1.0.0
structlog>=24.4.0
```

**requirements/dev.txt**
```
-r base.txt
pytest>=8.0.0
pytest-asyncio>=0.24.0
pytest-cov>=5.0.0
ruff>=0.7.0
mypy>=1.12.0
httpx>=0.27.0
pre-commit>=3.8.0
```

**requirements/agent_api.txt**
```
-r base.txt
langgraph>=0.2.0
langchain>=0.3.0
langchain-openai>=0.2.0
fastapi>=0.115.0
uvicorn[standard]>=0.32.0
sse-starlette>=2.1.0
azure-cosmos>=4.7.0
azure-identity>=1.18.0
azure-keyvault-secrets>=4.8.0
tavily-python>=0.5.0
httpx>=0.27.0
```

**requirements/mcp_common.txt**
```
-r base.txt
fastmcp>=2.0.0
```

**requirements/mcp_opportunities.txt**
```
-r mcp_common.txt
pyodbc>=5.1.0
# or pymssql, asyncpg, etc. depending on your DB
```

### Task 0.3: Create Root pyproject.toml

```toml
[project]
name = "invictus-ai-agent-platform"
version = "0.1.0"
description = "AI Copilot Agent Platform for Invictus AI"
requires-python = ">=3.11"

[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = [
    "E",      # pycodestyle errors
    "W",      # pycodestyle warnings
    "F",      # pyflakes
    "I",      # isort
    "B",      # flake8-bugbear
    "C4",     # flake8-comprehensions
    "UP",     # pyupgrade
    "ARG",    # flake8-unused-arguments
    "SIM",    # flake8-simplify
]
ignore = [
    "E501",   # line too long (handled by formatter)
    "B008",   # do not perform function calls in argument defaults
]

[tool.ruff.lint.isort]
known-first-party = ["agent_core", "agent_api", "mcp_common", "common"]

[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_ignores = true
disallow_untyped_defs = true
plugins = ["pydantic.mypy"]

[[tool.mypy.overrides]]
module = [
    "fastmcp.*",
    "langgraph.*",
    "langchain.*",
    "tavily.*",
    "azure.*",
]
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["packages", "apps"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
asyncio_mode = "auto"
addopts = "-v --tb=short"
```

### Task 0.4: Create Package pyproject.toml Files

**packages/agent_core/pyproject.toml**
```toml
[project]
name = "agent-core"
version = "0.1.0"
description = "Core agent graph and state management"
requires-python = ">=3.11"
dependencies = [
    "langgraph>=0.2.0",
    "langchain>=0.3.0",
    "langchain-openai>=0.2.0",
    "azure-cosmos>=4.7.0",
    "pydantic>=2.9.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
]

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

**packages/mcp_common/pyproject.toml**
```toml
[project]
name = "mcp-common"
version = "0.1.0"
description = "Shared utilities for MCP servers"
requires-python = ">=3.11"
dependencies = [
    "fastmcp>=2.0.0",
    "pydantic>=2.9.0",
    "structlog>=24.4.0",
]

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

**packages/common/pyproject.toml**
```toml
[project]
name = "common"
version = "0.1.0"
description = "Shared configuration, logging, and error handling"
requires-python = ">=3.11"
dependencies = [
    "pydantic>=2.9.0",
    "pydantic-settings>=2.5.0",
    "python-dotenv>=1.0.0",
    "structlog>=24.4.0",
]

[build-system]
requires = ["setuptools>=61.0"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

### Task 0.5: Create .gitignore

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# Virtual environments
.venv/
venv/
ENV/
env/

# IDE
.idea/
.vscode/
*.swp
*.swo
.DS_Store

# Testing
.pytest_cache/
.coverage
htmlcov/
.tox/
.nox/

# Type checking
.mypy_cache/
.dmypy.json
dmypy.json

# Environment
.env
.env.local
.env.*.local

# Azure
.azure/

# Logs
*.log
logs/

# Jupyter
.ipynb_checkpoints/

# Results files (we want to keep plans, but results are generated)
plans/results-*.md
```

### Task 0.6: Create .env.example

```env
# ===========================================
# Invictus AI Agent Platform - Environment
# ===========================================

# Azure OpenAI Configuration
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
AZURE_OPENAI_API_VERSION=2024-08-01-preview

# Cosmos DB Configuration
COSMOS_ENDPOINT=https://your-cosmos.documents.azure.com:443/
COSMOS_KEY=your-cosmos-key
COSMOS_DATABASE_NAME=invictus-copilot
COSMOS_SESSIONS_CONTAINER=sessions
COSMOS_CHECKPOINTS_CONTAINER=checkpoints
COSMOS_ARTIFACTS_CONTAINER=artifacts

# RAG Gateway Configuration
RAG_GATEWAY_URL=https://your-rag-gateway.azurewebsites.net
RAG_GATEWAY_API_KEY=your-rag-key

# Azure Key Vault (for production)
AZURE_KEY_VAULT_URL=https://your-keyvault.vault.azure.net/

# Tavily Search (optional)
TAVILY_API_KEY=your-tavily-key

# MCP Server Database Connections
# Opportunities DB
OPPORTUNITIES_DB_HOST=your-sql-server.database.windows.net
OPPORTUNITIES_DB_NAME=opportunities
OPPORTUNITIES_DB_USER=readonly_user
OPPORTUNITIES_DB_PASSWORD=your-password

# Clients DB
CLIENTS_DB_HOST=your-sql-server.database.windows.net
CLIENTS_DB_NAME=clients
CLIENTS_DB_USER=readonly_user
CLIENTS_DB_PASSWORD=your-password

# Application Settings
LOG_LEVEL=INFO
ENVIRONMENT=development
```

### Task 0.7: Create GitHub Actions CI Workflow

**.github/workflows/ci.yml**
```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main, develop]

jobs:
  lint-and-typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements/dev.txt
          pip install -e packages/common
          pip install -e packages/mcp_common
          pip install -e packages/agent_core

      - name: Run Ruff (linting)
        run: ruff check .

      - name: Run Ruff (formatting)
        run: ruff format --check .

      - name: Run MyPy
        run: mypy packages/ apps/ --ignore-missing-imports

  test:
    runs-on: ubuntu-latest
    needs: lint-and-typecheck
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -r requirements/dev.txt
          pip install -r requirements/agent_api.txt
          pip install -e packages/common
          pip install -e packages/mcp_common
          pip install -e packages/agent_core

      - name: Run tests
        run: pytest --cov=packages --cov=apps --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v4
        with:
          files: ./coverage.xml
          fail_ci_if_error: false
```

### Task 0.8: Create Local Development Script

**scripts/local_dev.sh**
```bash
#!/bin/bash
set -e

echo "=== Invictus AI Agent Platform - Local Development Setup ==="

# Check Python version
python_version=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
required_version="3.11"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "Error: Python $required_version or higher is required. Found: $python_version"
    exit 1
fi

echo "Python version: $python_version ✓"

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install development dependencies
echo "Installing development dependencies..."
pip install -r requirements/dev.txt

# Install shared packages in editable mode
echo "Installing shared packages..."
pip install -e packages/common
pip install -e packages/mcp_common
pip install -e packages/agent_core

# Install agent_api dependencies
echo "Installing agent_api dependencies..."
pip install -r requirements/agent_api.txt

# Copy .env.example if .env doesn't exist
if [ ! -f ".env" ]; then
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo "Please update .env with your actual configuration values."
fi

echo ""
echo "=== Setup Complete ==="
echo "Activate the virtual environment with: source .venv/bin/activate"
echo "Run the agent API with: uvicorn apps.agent_api.src.agent_api.main:app --reload"
```

### Task 0.9: Create Placeholder __init__.py Files

All `__init__.py` files should start with a simple docstring:

```python
"""Package initialization."""
```

### Task 0.10: Create Initial README.md

```markdown
# Invictus AI Agent Platform

AI Copilot Agent Platform for Invictus AI wealth management modules.

## Overview

This platform provides modular Copilot Agents that can be used across multiple Invictus AI modules:
- Deals
- Client Portal
- CRM
- Risk & Planning
- Admin

## Architecture

- **Agent API**: FastAPI service with LangGraph-based agent orchestration
- **MCP Servers**: Domain-specific tool servers (opportunities, clients, risk, reporting, admin)
- **RAG Gateway**: Integration with existing document retrieval service
- **Cosmos DB**: Session state, checkpoints, and artifact storage

## Quick Start

1. Clone the repository
2. Run the setup script:
   ```bash
   chmod +x scripts/local_dev.sh
   ./scripts/local_dev.sh
   ```
3. Update `.env` with your configuration
4. Start the agent API:
   ```bash
   source .venv/bin/activate
   uvicorn apps.agent_api.src.agent_api.main:app --reload
   ```

## Project Structure

```
├── apps/                  # Runnable services
│   ├── agent_api/        # Main Copilot API
│   └── mcp_servers/      # Domain MCP servers
├── packages/             # Shared libraries
│   ├── agent_core/       # LangGraph agent logic
│   ├── mcp_common/       # Shared MCP utilities
│   └── common/           # Config, logging, errors
├── infra/                # Azure infrastructure (Bicep)
├── docs/                 # Documentation
├── scripts/              # Development utilities
└── plans/                # Implementation plans
```

## Development

### Running Tests
```bash
pytest
```

### Linting
```bash
ruff check .
ruff format .
```

### Type Checking
```bash
mypy packages/ apps/
```

## Documentation

- [Architecture](docs/architecture.md)
- [Tool Catalog](docs/tool-catalog.md)
- [Streaming Events](docs/streaming-events.md)
- [Security](docs/security.md)
```

---

## Azure Configuration Checklist

Before moving to Phase 1, complete the following Azure setup:

### 1. Cosmos DB Setup

```bash
# Using Azure CLI
az cosmosdb sql database create \
  --account-name <your-cosmos-account> \
  --resource-group <your-rg> \
  --name invictus-copilot

# Create containers
az cosmosdb sql container create \
  --account-name <your-cosmos-account> \
  --resource-group <your-rg> \
  --database-name invictus-copilot \
  --name sessions \
  --partition-key-path /tenant_id

az cosmosdb sql container create \
  --account-name <your-cosmos-account> \
  --resource-group <your-rg> \
  --database-name invictus-copilot \
  --name checkpoints \
  --partition-key-path /session_id

az cosmosdb sql container create \
  --account-name <your-cosmos-account> \
  --resource-group <your-rg> \
  --database-name invictus-copilot \
  --name artifacts \
  --partition-key-path /tenant_id
```

### 2. Key Vault Setup (if not exists)

Add the following secrets to Azure Key Vault:
- `cosmos-key`: Cosmos DB primary key
- `openai-api-key`: Azure OpenAI API key
- `rag-gateway-key`: RAG Gateway API key
- `tavily-api-key`: Tavily API key (if using)
- `opportunities-db-password`: Opportunities DB password
- `clients-db-password`: Clients DB password

### 3. Collect Connection Strings

Update your `.env` file with:
- Cosmos DB endpoint and key
- Azure OpenAI endpoint and deployment name
- RAG Gateway URL
- Database connection details for MCP servers

---

## Testing Checklist

- [ ] All directories created as per structure
- [ ] Virtual environment created and activated
- [ ] All dependencies installed without errors
- [ ] `ruff check .` passes with no errors
- [ ] `ruff format --check .` passes
- [ ] `mypy packages/ apps/` passes (may have warnings initially)
- [ ] `pytest` runs (may have no tests yet)
- [ ] GitHub Actions CI workflow runs successfully
- [ ] `.env` file created from `.env.example`

---

## Expected Deliverables

After completing Phase 0:

1. **Complete folder structure** matching the architecture document
2. **Requirements files** with proper dependency organization
3. **Development tooling** configured (ruff, mypy, pytest)
4. **CI workflow** running on GitHub
5. **Environment template** with all required variables
6. **Local development script** for easy onboarding
7. **Cosmos DB collections** created in Azure
8. **README** with project overview and setup instructions

---

## Next Phase

Once Phase 0 is complete and tested, proceed to [Phase 1: MVP Copilot + Streaming](phase-1-mvp-copilot-streaming.md).
