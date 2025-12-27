# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Development Commands

```bash
# Setup (first time)
chmod +x scripts/local_dev.sh && ./scripts/local_dev.sh

# Activate virtual environment
source .venv/bin/activate

# Run agent API
uvicorn apps.agent_api.src.agent_api.main:app --reload

# Run all tests
pytest

# Run a single test file
pytest packages/agent_core/tests/test_specific.py -v

# Run tests matching a pattern
pytest -k "test_pattern" -v

# Linting
ruff check .
ruff format .

# Type checking
mypy packages/ apps/
```

## Architecture Overview

This is a **LangGraph-based multi-agent AI copilot** for wealth management. The system has three layers:

```
FastAPI (apps/agent_api)  →  LangGraph Agent (packages/agent_core)  →  Tools (MCP, RAG, Web)
```

### Request Flow

1. **API Layer** (`apps/agent_api/src/agent_api/api/routes.py`): Receives requests at `/v1/copilot/chat` or `/stream`
2. **Graph Orchestrator** (`packages/agent_core/src/agent_core/graph/base_graph.py`): Routes through subgraphs
3. **Tools** fetch data from MCP servers, RAG Gateway, and Tavily web search
4. **Results** stream back via SSE or return in response

### Two Request Modes

- **Ask Mode** (`type: "ask"`): Conversational Q&A with tool access
- **Agent Mode** (`type: "agent"`): Document creation (`agent_case: "create"`) or editing (`agent_case: "edit"`)

### State Management

All graph nodes share state via `MultiAgentState` TypedDict defined in `packages/agent_core/src/agent_core/graph/state.py`. Key state fields:
- `messages`: Chat history
- `working_memory`: Accumulated context from tools
- `mcp_data`, `rag_data`, `web_data`: Tool results
- `tool_results`: Audit trail of tool calls

## Key Packages

| Package | Purpose |
|---------|---------|
| `packages/agent_core` | LangGraph graph, subgraphs, nodes, tools |
| `packages/common` | Config (`config.py`), logging, errors |
| `apps/agent_api` | FastAPI routes, schemas, SSE streaming |
| `apps/mcp_servers/deals` | FastMCP server for deals domain |

## Graph Subgraphs

Located in `packages/agent_core/src/agent_core/graph/subgraphs/`:

- `ask_handler/`: Handles simple Q&A requests (gather context → generate answer)
- `intent_analyzer/`: Detects user intent
- `data_retrieval/`: Parallel agents for MCP, RAG, and web data
- `planning/`: Creates execution plans for agent mode
- `clarification/`: Generates clarification questions
- `confirmation/`: HITL plan approval
- `template_manager/`, `section_writer/`, `review/`, `source_mapper/`: Document generation pipeline

## Tools

| Tool | File | Purpose |
|------|------|---------|
| RAG Gateway | `tools/rag_gateway.py` | Document field extraction |
| MCP Client | `tools/mcp_client.py` | Call domain MCP servers |
| Deals MCP | `tools/deals_mcp.py` | Deals-specific MCP wrapper |
| Web Search | `tools/web_search.py` | Tavily web search |

## API Schemas

Defined in `apps/agent_api/src/agent_api/api/schemas.py`:

- `UnifiedChatRequest`: Main request schema (supports both ask and agent modes)
- `ChatResponse`: Response with message, tool_results, citations
- `SSEEventType`: 25+ event types for streaming updates

## Environment Configuration

Configuration loaded via Pydantic Settings in `packages/common/src/common/config.py`. Key variables:
- `AZURE_OPENAI_*`: LLM configuration
- `COSMOS_*`: Session/checkpoint persistence
- `RAG_GATEWAY_URL`: Document retrieval
- `MCP_DEALS_URL`: Deals MCP server
- `TAVILY_API_KEY`: Optional web search

## PYTHONPATH for Running Scripts

When running scripts directly, set PYTHONPATH:
```bash
PYTHONPATH="apps/agent_api/src:packages/agent_core/src:packages/common/src:packages/mcp_common/src" python3 your_script.py
```

## Code Style

- Python 3.11+ with full type hints
- Async-first (all I/O operations are async)
- Ruff for linting (line-length: 100)
- Structured logging via `common.logging.get_logger(__name__)`
