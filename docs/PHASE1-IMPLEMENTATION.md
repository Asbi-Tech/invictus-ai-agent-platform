# Phase 1 Implementation: MVP Copilot + Streaming + Cosmos Memory

**Date:** December 25, 2024
**Status:** Complete
**Version:** 0.1.0

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Components Built](#components-built)
4. [API Reference](#api-reference)
5. [Testing Guide](#testing-guide)
6. [Configuration](#configuration)
7. [What's Pending](#whats-pending)
8. [Troubleshooting](#troubleshooting)

---

## Overview

Phase 1 implements the core AI Copilot functionality for the Invictus wealth management platform. The system provides:

- **Conversational AI**: Natural language interface for wealth management queries
- **Intent Classification**: Automatically routes requests based on user intent (Q&A, summarization, generation, etc.)
- **Session Persistence**: Maintains conversation history across requests using Cosmos DB
- **Real-time Streaming**: Server-Sent Events (SSE) for progressive response delivery
- **Extensible Tool System**: Framework for RAG and MCP tool integration

### Key Technologies

| Technology | Purpose |
|------------|---------|
| **LangGraph** | Agent orchestration and state management |
| **Azure OpenAI** | GPT-4o for intent classification and response generation |
| **Cosmos DB** | Session checkpoints and conversation persistence |
| **FastAPI** | REST API with SSE streaming support |
| **Pydantic** | Request/response validation and settings management |
| **structlog** | Structured JSON logging |

---

## Architecture

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              Client                                      │
│                    (Frontend / API Consumer)                             │
└─────────────────────────────────┬───────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         FastAPI Service                                  │
│                    (apps/agent_api/src/agent_api/)                       │
│                                                                          │
│   ┌──────────────────┐  ┌──────────────────┐  ┌────────────────────┐    │
│   │  POST /v1/       │  │  POST /v1/       │  │  /v1/sessions      │    │
│   │  copilot/chat    │  │  copilot/stream  │  │  (CRUD)            │    │
│   └────────┬─────────┘  └────────┬─────────┘  └────────────────────┘    │
│            │                     │                                       │
└────────────┼─────────────────────┼──────────────────────────────────────┘
             │                     │
             ▼                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      LangGraph StateGraph                                │
│               (packages/agent_core/src/agent_core/graph/)                │
│                                                                          │
│   ┌────────────────┐                                                     │
│   │ ingest_context │  Parse request, extract page context & documents    │
│   └───────┬────────┘                                                     │
│           │                                                              │
│           ▼                                                              │
│   ┌────────────────┐                                                     │
│   │  route_intent  │  LLM classifies: qa|summarize|generate|edit|compare │
│   └───────┬────────┘                                                     │
│           │                                                              │
│           ▼                                                              │
│   ┌────────────────┐                                                     │
│   │ gather_context │  Call RAG Gateway / MCP servers for data            │
│   └───────┬────────┘                                                     │
│           │                                                              │
│           ▼                                                              │
│   ┌────────────────┐                                                     │
│   │draft_or_answer │  LLM generates contextual response                  │
│   └───────┬────────┘                                                     │
│           │                                                              │
│           ▼                                                              │
│   ┌────────────────┐                                                     │
│   │    finalize    │  Prepare response, collect citations & artifacts    │
│   └───────┬────────┘                                                     │
│           │                                                              │
│           ▼                                                              │
│        [END]                                                             │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                          Cosmos DB                                       │
│                                                                          │
│   ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐         │
│   │   checkpoints   │  │    sessions     │  │   artifacts     │         │
│   │  (LangGraph     │  │  (Session       │  │  (Generated     │         │
│   │   state)        │  │   metadata)     │  │   documents)    │         │
│   └─────────────────┘  └─────────────────┘  └─────────────────┘         │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Package Structure

```
invictus-ai-agent-platform/
├── apps/
│   └── agent_api/                    # FastAPI application
│       └── src/agent_api/
│           ├── main.py               # App entry point, lifespan, health check
│           └── api/
│               ├── schemas.py        # Pydantic models for requests/responses
│               └── routes.py         # API endpoint handlers
│
├── packages/
│   ├── common/                       # Shared utilities
│   │   └── src/common/
│   │       ├── config.py             # Settings with pydantic-settings
│   │       ├── logging.py            # Structured logging setup
│   │       └── errors.py             # Custom exception classes
│   │
│   ├── agent_core/                   # Core agent logic
│   │   └── src/agent_core/
│   │       ├── state/
│   │       │   └── models.py         # AgentState TypedDict
│   │       ├── memory/
│   │       │   └── cosmos_checkpointer.py  # LangGraph checkpoint storage
│   │       ├── tools/
│   │       │   ├── rag_gateway.py    # RAG ExtractFields client
│   │       │   └── mcp_client.py     # MCP server client
│   │       └── graph/
│   │           ├── base_graph.py     # StateGraph definition
│   │           └── nodes/
│   │               ├── ingest_context.py
│   │               ├── route_intent.py
│   │               ├── gather_context.py
│   │               ├── draft_or_answer.py
│   │               └── finalize.py
│   │
│   └── mcp_common/                   # MCP server utilities
│       └── src/mcp_common/
│           ├── auth.py               # Token validation
│           └── telemetry.py          # OpenTelemetry setup
│
└── docs/
    └── PHASE1-IMPLEMENTATION.md      # This file
```

---

## Components Built

### 1. FastAPI Service (`apps/agent_api/`)

The HTTP layer that exposes the Copilot functionality.

#### Files:

| File | Description |
|------|-------------|
| `main.py` | Application factory, CORS setup, health endpoint |
| `api/schemas.py` | Pydantic models for all request/response types |
| `api/routes.py` | Route handlers for chat, stream, and sessions |

#### Key Features:
- CORS enabled for cross-origin requests
- Health check endpoint at `/health`
- Lazy initialization of agent and checkpointer
- Proper error handling with detailed responses

### 2. Agent Core (`packages/agent_core/`)

The LangGraph-based agent that processes requests.

#### State Model (`state/models.py`)

```python
class AgentState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]  # Conversation history
    tenant_id: str                    # Multi-tenant isolation
    user_id: str                      # User identifier
    session_id: str                   # Session for continuity
    current_intent: str               # Classified intent
    page_context: dict                # UI context (module, screen, entity)
    selected_docs: dict               # Documents for RAG
    tool_results: list[dict]          # Results from tool calls
    working_memory: dict              # Scratch space for processing
    tool_policy: dict                 # Permissions and limits
    artifacts: list[dict]             # Generated documents
    tool_call_count: int              # Tracking for limits
    error_count: int                  # Error tracking
```

#### Graph Nodes

| Node | File | Purpose |
|------|------|---------|
| `ingest_context` | `nodes/ingest_context.py` | Parse request, extract page context |
| `route_intent` | `nodes/route_intent.py` | LLM-based intent classification |
| `gather_context` | `nodes/gather_context.py` | Call RAG/MCP tools for data |
| `draft_or_answer` | `nodes/draft_or_answer.py` | Generate response with LLM |
| `finalize` | `nodes/finalize.py` | Prepare final output |

#### Intent Classification

The `route_intent` node uses GPT-4o to classify user messages into:

| Intent | Description | Example Triggers |
|--------|-------------|------------------|
| `qa` | Question answering | "What is...", "How does...", "Tell me about..." |
| `summarize` | Content summarization | "Summarize...", "Give me a brief...", "Overview of..." |
| `generate` | Content creation | "Create...", "Draft...", "Write..." |
| `edit` | Content modification | "Edit...", "Modify...", "Update..." |
| `compare` | Comparison analysis | "Compare...", "Difference between...", "X vs Y" |

### 3. Cosmos DB Checkpointer (`memory/cosmos_checkpointer.py`)

Implements LangGraph's `BaseCheckpointSaver` interface for persistent sessions.

#### Features:
- Stores full conversation state per session
- Supports checkpoint versioning with `checkpoint_ns` and `checkpoint_id`
- Async methods for non-blocking operations
- Partition key: `/thread_id` for efficient queries

#### Schema:

```json
{
  "id": "<checkpoint_id>",
  "thread_id": "<session_id>",
  "checkpoint_ns": "",
  "checkpoint": { /* serialized state */ },
  "metadata": { /* step info */ },
  "parent_checkpoint_id": "<previous_checkpoint_id>"
}
```

### 4. Tools (`tools/`)

#### RAG Gateway Client (`rag_gateway.py`)

Calls the ExtractFields API for document analysis:

```python
async def extract_fields(
    tenant_id: str,
    doc_ids: list[str],
    fields: list[FieldDefinition],
    storage: StorageConfig,
    user_id: str = "",
    session_id: str = "",
) -> ExtractFieldsResponse
```

#### MCP Client (`mcp_client.py`)

Framework for calling Model Context Protocol servers:

```python
class MCPClient:
    async def call_tool(self, tool_name: str, arguments: dict) -> dict
    async def list_tools(self) -> list[dict]
```

### 5. Common Utilities (`packages/common/`)

#### Configuration (`config.py`)

Uses `pydantic-settings` to load from environment:

```python
settings = get_settings()
settings.azure_openai_endpoint    # Azure OpenAI URL
settings.cosmos_endpoint          # Cosmos DB URL
settings.rag_gateway_url          # RAG Gateway URL
```

#### Logging (`logging.py`)

Structured JSON logging with context:

```python
logger = get_logger(__name__)
logger.info("Processing request", session_id=session_id, tenant_id=tenant_id)
```

Output:
```json
{
  "timestamp": "2025-12-25T10:19:16.314059Z",
  "level": "info",
  "message": "Processing request",
  "session_id": "109edc0b-dcb4-42c8-9d1d-c1c83f84ba29",
  "tenant_id": "test-tenant"
}
```

---

## API Reference

### Base URL

```
http://localhost:8000
```

### Endpoints

#### 1. Health Check

```http
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "0.1.0",
  "environment": "development"
}
```

---

#### 2. Chat (Non-Streaming)

```http
POST /v1/copilot/chat
Content-Type: application/json
```

**Request Body:**

```json
{
  "message": "What investment opportunities are available for high-net-worth clients?",
  "tenant_id": "acme-corp",
  "user_id": "user-123",
  "session_id": "optional-session-uuid",
  "internet_search_enabled": false,
  "page_context": {
    "module_id": "opportunities",
    "screen_name": "OpportunityList",
    "entity_type": "opportunity",
    "entity_id": "opp-456",
    "additional_context": {"filter": "high-value"}
  },
  "selected_docs": {
    "doc_ids": ["doc-001", "doc-002"],
    "doc_sets": ["quarterly-reports"],
    "storage": {
      "account_url": "https://storage.blob.core.windows.net",
      "filesystem": "documents",
      "base_prefix": "clients/acme"
    }
  }
}
```

**Request Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `message` | string | Yes | User's message |
| `tenant_id` | string | Yes | Tenant identifier for multi-tenancy |
| `user_id` | string | Yes | User identifier |
| `session_id` | string | No | Session ID for conversation continuity |
| `internet_search_enabled` | boolean | No | Enable Tavily web search (default: false) |
| `page_context` | object | No | Current UI context |
| `selected_docs` | object | No | Documents for RAG analysis |

**Response:**

```json
{
  "session_id": "109edc0b-dcb4-42c8-9d1d-c1c83f84ba29",
  "message": "Based on current market conditions, here are the top investment opportunities for high-net-worth clients...",
  "tool_results": [
    {
      "tool_name": "rag_extract_fields",
      "input_summary": "Extracted investment data from 2 documents",
      "output_summary": "Found 5 investment opportunities",
      "latency_ms": 1250,
      "success": true,
      "citations": [
        {
          "doc_id": "doc-001",
          "title": "Q4 Investment Report",
          "snippet": "Private equity allocation increased by 15%..."
        }
      ]
    }
  ],
  "citations": [...],
  "intent": "qa"
}
```

---

#### 3. Stream (SSE)

```http
POST /v1/copilot/stream
Content-Type: application/json
Accept: text/event-stream
```

**Request Body:** Same as `/chat`

**Response:** Server-Sent Events stream

```
event: status
data: {"event_type": "status", "data": {"status": "processing", "session_id": "..."}, "timestamp": "..."}

event: status
data: {"event_type": "status", "data": {"status": "gathering_context"}, "timestamp": "..."}

event: tool_call_result
data: {"event_type": "tool_call_result", "data": {"tool_name": "rag_extract_fields", "success": true, "latency_ms": 1250}, "timestamp": "..."}

event: status
data: {"event_type": "status", "data": {"status": "generating_response"}, "timestamp": "..."}

event: assistant_delta
data: {"event_type": "assistant_delta", "data": {"content": "Based on current "}, "timestamp": "..."}

event: assistant_delta
data: {"event_type": "assistant_delta", "data": {"content": "market conditions..."}, "timestamp": "..."}

event: final
data: {"event_type": "final", "data": {"session_id": "...", "message": "...", "tool_call_count": 1, "intent": "qa"}, "timestamp": "..."}
```

**SSE Event Types:**

| Event Type | Description |
|------------|-------------|
| `status` | Processing status updates |
| `tool_call_result` | Results from tool invocations |
| `assistant_delta` | Incremental response chunks |
| `final` | Complete response with metadata |
| `error` | Error information |

---

#### 4. Create Session

```http
POST /v1/copilot/sessions
Content-Type: application/json
```

**Request:**
```json
{
  "tenant_id": "acme-corp",
  "user_id": "user-123"
}
```

**Response:**
```json
{
  "session_id": "new-uuid",
  "tenant_id": "acme-corp",
  "user_id": "user-123",
  "created_at": "2025-12-25T10:00:00Z",
  "message_count": 0
}
```

---

#### 5. Get Session

```http
GET /v1/copilot/sessions/{session_id}
```

**Response:**
```json
{
  "session_id": "109edc0b-dcb4-42c8-9d1d-c1c83f84ba29",
  "tenant_id": "acme-corp",
  "user_id": "user-123",
  "created_at": "2025-12-25T10:00:00Z",
  "message_count": 5
}
```

---

## Testing Guide

### Prerequisites

1. **Environment Setup:**
   ```bash
   cd /Users/raoof/Documents/work/space/invictus-ai-agent-platform
   source .venv/bin/activate
   ```

2. **Environment Variables:**
   Ensure `.env` file has all required values (see Configuration section)

3. **Cosmos DB Containers:**
   - `checkpoints` (partition key: `/thread_id`)
   - `sessions` (partition key: `/tenant_id`)
   - `artifacts` (partition key: `/session_id`)

### Running the Server

```bash
# Set Python path
export PYTHONPATH="apps/agent_api/src:packages/agent_core/src:packages/common/src:packages/mcp_common/src"

# Start server (with hot reload for development)
uvicorn agent_api.main:app --reload --port 8000
```

### Test Cases

#### Test 1: Health Check

```bash
curl http://localhost:8000/health
```

**Expected:**
```json
{"status":"healthy","version":"0.1.0","environment":"development"}
```

---

#### Test 2: Basic Chat

```bash
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hello, what can you help me with?",
    "tenant_id": "test-tenant",
    "user_id": "test-user"
  }'
```

**Expected:** JSON response with greeting and capabilities list

---

#### Test 3: Session Continuity

First request - introduce yourself:
```bash
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "My name is John and I am interested in tech stocks",
    "tenant_id": "test-tenant",
    "user_id": "test-user"
  }'
```

Note the `session_id` from the response.

Second request - test memory:
```bash
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is my name and what am I interested in?",
    "tenant_id": "test-tenant",
    "user_id": "test-user",
    "session_id": "<session_id_from_first_request>"
  }'
```

**Expected:** Response should mention "John" and "tech stocks"

---

#### Test 4: Intent Classification

Test different intents:

```bash
# Q&A Intent
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is a mutual fund?", "tenant_id": "t", "user_id": "u"}'
# Expected intent: "qa"

# Summarize Intent
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Summarize the key points of portfolio diversification", "tenant_id": "t", "user_id": "u"}'
# Expected intent: "summarize"

# Generate Intent
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Create a memo about the new investment policy", "tenant_id": "t", "user_id": "u"}'
# Expected intent: "generate"

# Compare Intent
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Compare ETFs vs mutual funds", "tenant_id": "t", "user_id": "u"}'
# Expected intent: "compare"
```

---

#### Test 5: SSE Streaming

```bash
curl -N -X POST http://localhost:8000/v1/copilot/stream \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Explain the benefits of index funds",
    "tenant_id": "test-tenant",
    "user_id": "test-user"
  }'
```

**Expected:** Stream of SSE events with status updates and progressive response

---

#### Test 6: Page Context

```bash
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Tell me about this opportunity",
    "tenant_id": "test-tenant",
    "user_id": "test-user",
    "page_context": {
      "module_id": "opportunities",
      "screen_name": "OpportunityDetail",
      "entity_type": "opportunity",
      "entity_id": "opp-12345"
    }
  }'
```

**Expected:** Response acknowledges the opportunity context

---

#### Test 7: With Document Selection (RAG Ready)

```bash
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What are the key findings in these documents?",
    "tenant_id": "test-tenant",
    "user_id": "test-user",
    "selected_docs": {
      "doc_ids": ["doc-001", "doc-002"],
      "storage": {
        "account_url": "https://yourstorage.blob.core.windows.net",
        "filesystem": "documents",
        "base_prefix": "reports"
      }
    }
  }'
```

**Note:** RAG extraction is prepared but will only execute when the RAG Gateway is configured and accessible.

---

### Verifying Cosmos DB Storage

After running tests, verify data in Cosmos DB:

1. Open Azure Portal → Cosmos DB → `cosmos-invictus-uaenorth-dev`
2. Navigate to `invictus-copilot` database
3. Check `checkpoints` container for stored sessions

Query example:
```sql
SELECT * FROM c WHERE c.thread_id = '<session_id>'
```

---

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# ===========================================
# Environment
# ===========================================
ENVIRONMENT=development
LOG_LEVEL=INFO

# ===========================================
# Azure OpenAI Configuration
# ===========================================
AZURE_OPENAI_ENDPOINT=https://your-openai.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
AZURE_OPENAI_API_VERSION=2024-02-01

# ===========================================
# Cosmos DB Configuration
# ===========================================
COSMOS_ENDPOINT=https://your-cosmos.documents.azure.com:443/
COSMOS_KEY=your-cosmos-key
COSMOS_DATABASE_NAME=invictus-copilot
COSMOS_SESSIONS_CONTAINER=sessions
COSMOS_CHECKPOINTS_CONTAINER=checkpoints
COSMOS_ARTIFACTS_CONTAINER=artifacts

# ===========================================
# RAG Gateway Configuration
# ===========================================
RAG_GATEWAY_URL=https://your-rag-function.azurewebsites.net/api
RAG_GATEWAY_API_KEY=optional-api-key

# ===========================================
# MCP Server URLs (Future)
# ===========================================
MCP_OPPORTUNITIES_URL=http://localhost:8001
MCP_CLIENTS_URL=http://localhost:8002
MCP_RISK_PLANNING_URL=http://localhost:8003
```

### Cosmos DB Setup

Create containers with the following partition keys:

| Container | Partition Key | Purpose |
|-----------|---------------|---------|
| `checkpoints` | `/thread_id` | LangGraph state storage |
| `sessions` | `/tenant_id` | Session metadata |
| `artifacts` | `/session_id` | Generated documents |

Azure CLI command:
```bash
az cosmosdb sql container create \
  --account-name cosmos-invictus-uaenorth-dev \
  --database-name invictus-copilot \
  --name checkpoints \
  --partition-key-path /thread_id \
  --resource-group IDT-MVP
```

---

## What's Pending

### Phase 1 Remaining Items

| Item | Description | Priority |
|------|-------------|----------|
| RAG Integration | Connect `gather_context` to live ExtractFields API | High |
| MCP Servers | Build domain servers when DB credentials available | High |
| Session CRUD | Full session management in `sessions` container | Medium |
| Error Handling | Enhanced error responses with error codes | Medium |

### Future Phases

| Phase | Features |
|-------|----------|
| **Phase 2** | Tool orchestration, retry logic, parallel execution, tool result caching |
| **Phase 3** | Artifact generation (reports, memos), PDF/DOCX export, artifact versioning |
| **Phase 4** | Multi-agent architecture, specialized sub-agents, agent handoff |
| **Phase 5** | Observability with Azure Application Insights, OpenTelemetry tracing |
| **Phase 6** | Admin tools, policy management, usage analytics |

---

## Troubleshooting

### Common Issues

#### 1. Module Not Found Error

```
ModuleNotFoundError: No module named 'agent_api'
```

**Solution:** Set the PYTHONPATH:
```bash
export PYTHONPATH="apps/agent_api/src:packages/agent_core/src:packages/common/src:packages/mcp_common/src"
```

---

#### 2. Cosmos DB Connection Error

```
CosmosResourceNotFoundError: Container not found
```

**Solution:** Create the required containers:
```bash
az cosmosdb sql container create \
  --account-name cosmos-invictus-uaenorth-dev \
  --database-name invictus-copilot \
  --name checkpoints \
  --partition-key-path /thread_id \
  --resource-group IDT-MVP
```

---

#### 3. Azure OpenAI Authentication Error

```
openai.AuthenticationError: Incorrect API key
```

**Solution:** Verify `.env` has correct Azure OpenAI credentials:
```bash
AZURE_OPENAI_ENDPOINT=https://your-instance.openai.azure.com/
AZURE_OPENAI_API_KEY=your-actual-key
AZURE_OPENAI_DEPLOYMENT_NAME=your-deployment-name
```

---

#### 4. Port Already in Use

```
OSError: [Errno 48] Address already in use
```

**Solution:** Kill existing process:
```bash
pkill -f uvicorn
# or
lsof -i :8000 | grep LISTEN | awk '{print $2}' | xargs kill
```

---

#### 5. SSE Connection Drops

If streaming connection drops prematurely:

**Solution:** Ensure client supports SSE and has appropriate timeout:
```javascript
const eventSource = new EventSource('/v1/copilot/stream', {
  // Increase timeout if needed
});
```

---

### Logging

View detailed logs by setting log level:

```bash
export LOG_LEVEL=DEBUG
uvicorn agent_api.main:app --reload
```

Logs are structured JSON for easy parsing:
```json
{
  "timestamp": "2025-12-25T10:19:16.314059Z",
  "level": "info",
  "event": "Processing chat request",
  "session_id": "109edc0b-dcb4-42c8-9d1d-c1c83f84ba29",
  "tenant_id": "test-tenant",
  "message_preview": "Hello, what can you help me with?"
}
```

---

## Appendix

### Quick Start Script

Create a `run-dev.sh` script:

```bash
#!/bin/bash
set -e

cd /Users/raoof/Documents/work/space/invictus-ai-agent-platform
source .venv/bin/activate

export PYTHONPATH="apps/agent_api/src:packages/agent_core/src:packages/common/src:packages/mcp_common/src"

echo "Starting Invictus AI Copilot API..."
uvicorn agent_api.main:app --reload --host 0.0.0.0 --port 8000
```

Make it executable:
```bash
chmod +x run-dev.sh
./run-dev.sh
```

---

### API Client Example (Python)

```python
import httpx
import json

BASE_URL = "http://localhost:8000"

# Non-streaming chat
async def chat(message: str, tenant_id: str, user_id: str, session_id: str = None):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/v1/copilot/chat",
            json={
                "message": message,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "session_id": session_id,
            },
            timeout=60.0,
        )
        return response.json()

# Streaming chat
async def stream_chat(message: str, tenant_id: str, user_id: str):
    async with httpx.AsyncClient() as client:
        async with client.stream(
            "POST",
            f"{BASE_URL}/v1/copilot/stream",
            json={
                "message": message,
                "tenant_id": tenant_id,
                "user_id": user_id,
            },
            timeout=60.0,
        ) as response:
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    event_data = json.loads(line[5:].strip())
                    yield event_data
```

---

### Frontend Integration (TypeScript)

```typescript
interface ChatRequest {
  message: string;
  tenant_id: string;
  user_id: string;
  session_id?: string;
  page_context?: {
    module_id: string;
    screen_name: string;
    entity_type?: string;
    entity_id?: string;
  };
}

// SSE Streaming
function streamChat(request: ChatRequest, onChunk: (chunk: string) => void) {
  const eventSource = new EventSource('/v1/copilot/stream', {
    // Note: EventSource doesn't support POST, use fetch with ReadableStream instead
  });

  // For POST with SSE, use fetch:
  fetch('/v1/copilot/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  }).then(response => {
    const reader = response.body?.getReader();
    const decoder = new TextDecoder();

    function read() {
      reader?.read().then(({ done, value }) => {
        if (done) return;
        const chunk = decoder.decode(value);
        // Parse SSE events
        const lines = chunk.split('\n');
        for (const line of lines) {
          if (line.startsWith('data:')) {
            const eventData = JSON.parse(line.slice(5).trim());
            if (eventData.event_type === 'assistant_delta') {
              onChunk(eventData.data.content);
            }
          }
        }
        read();
      });
    }
    read();
  });
}
```

---

*Last updated: December 25, 2024*
