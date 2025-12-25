# Invictus AI Agent Platform

AI Copilot Agent Platform for Invictus AI wealth management modules.

## Overview

This platform provides modular Copilot Agents that can be used across multiple Invictus AI modules:

- **Deals** - Opportunity analysis, investment memos, due diligence
- **Client Portal** - Client Q&A, portfolio insights
- **CRM** - Client relationship intelligence
- **Risk & Planning** - IPS analysis, risk profiling
- **Admin** - Policy management, user permissions

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Frontend Modules                         │
│         (Deals, CRM, Client Portal, Risk, Admin)            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Agent API (FastAPI)                       │
│    ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐  │
│    │  SSE Stream │  │ Session Mgmt │  │  HITL Handler   │  │
│    └─────────────┘  └──────────────┘  └─────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                   Agent Core (LangGraph)                     │
│    ┌─────────┐  ┌──────────┐  ┌───────────┐  ┌──────────┐  │
│    │ Ingest  │→ │  Route   │→ │  Gather   │→ │  Draft   │  │
│    │ Context │  │  Intent  │  │  Context  │  │  Answer  │  │
│    └─────────┘  └──────────┘  └───────────┘  └──────────┘  │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│   RAG Gateway   │ │   MCP Servers   │ │  Tavily Search  │
│  (Existing)     │ │  (FastMCP)      │ │  (Optional)     │
└─────────────────┘ └─────────────────┘ └─────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  Opportunities  │ │    Clients      │ │  Risk/Reporting │
│       DB        │ │       DB        │ │       DB        │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

## Tech Stack

- **Agent Orchestration**: LangGraph + LangChain
- **API Framework**: FastAPI with SSE streaming
- **MCP Servers**: FastMCP
- **Storage**: Azure Cosmos DB (sessions, checkpoints, artifacts)
- **Vector Search**: Azure AI Search (via RAG Gateway)
- **LLM**: Azure OpenAI
- **Infrastructure**: Azure Container Apps

## Quick Start

### Prerequisites

- Python 3.11+
- Azure subscription with:
  - Azure OpenAI
  - Cosmos DB
  - Access to RAG Gateway

### Setup

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd invictus-ai-agent-platform
   ```

2. Run the setup script:
   ```bash
   chmod +x scripts/local_dev.sh
   ./scripts/local_dev.sh
   ```

3. Update `.env` with your configuration:
   ```bash
   # Edit .env with your actual values
   nano .env
   ```

4. Start the agent API:
   ```bash
   source .venv/bin/activate
   uvicorn apps.agent_api.src.agent_api.main:app --reload
   ```

## Project Structure

```
invictus-ai-agent-platform/
├── apps/                          # Runnable services
│   ├── agent_api/                 # Main Copilot API (FastAPI)
│   └── mcp_servers/               # Domain MCP servers
│       ├── opportunities/         # Deals/opportunities data
│       ├── clients/               # Client profiles & portfolios
│       ├── risk_planning/         # IPS, IPQ, risk profiles
│       ├── reporting/             # Report templates & history
│       └── admin_policy/          # Tenant policies & permissions
│
├── packages/                      # Shared libraries
│   ├── agent_core/                # LangGraph agent, state, tools
│   ├── mcp_common/                # Shared MCP utilities & models
│   └── common/                    # Config, logging, errors
│
├── requirements/                  # Dependency files
├── infra/                         # Azure infrastructure (Bicep)
├── docs/                          # Documentation
├── scripts/                       # Development utilities
└── plans/                         # Implementation plans
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

## Implementation Phases

| Phase | Focus | Status |
|-------|-------|--------|
| 0 | Repo scaffolding & CI | In Progress |
| 1 | MVP Copilot + Streaming + Cosmos | Pending |
| 2 | Content Generation + Artifacts | Pending |
| 3 | HITL + Tool Governance | Pending |
| 4 | MCP Ecosystem Expansion | Pending |
| 5 | Production Hardening | Pending |

See the [plans/](plans/) directory for detailed implementation plans.

## Documentation

- [Architecture](docs/architecture.md)
- [Tool Catalog](docs/tool-catalog.md)
- [Streaming Events](docs/streaming-events.md)
- [Security](docs/security.md)
- [Runbooks](docs/runbooks.md)

## License

Proprietary - Invictus AI
