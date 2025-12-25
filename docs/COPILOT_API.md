# Invictus Copilot API

A LangGraph-based AI agent platform supporting conversational (Ask) and document generation (Agent) modes with real-time SSE streaming.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [API Endpoints](#api-endpoints)
- [Request Types](#request-types)
- [SSE Events](#sse-events)
- [Graph Flow](#graph-flow)
- [Tools](#tools)
- [Usage Examples](#usage-examples)
- [Configuration](#configuration)

---

## Overview

The Copilot API provides two primary modes of interaction:

| Mode | Purpose | Output |
|------|---------|--------|
| **Ask** | Conversational Q&A with RAG and tool access | Text response with citations |
| **Agent (Create)** | Generate new documents/artifacts | Structured artifact (memo, report, etc.) |
| **Agent (Edit)** | Modify existing artifacts | Diff-based edit instructions |

All modes support real-time SSE streaming with "thinking" status updates.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         FastAPI Router                          │
│                    /v1/copilot/chat, /stream                    │
└─────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      LangGraph Agent                            │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │ingest_context│───▶│route_request │───▶│  ASK / AGENT     │  │
│  └──────────────┘    └──────────────┘    │  Flow Nodes      │  │
│                                          └──────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
   ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
   │   Deals MCP      │ │   RAG Gateway    │ │   Tavily         │
   │   (Mock Tools)   │ │   (Doc Search)   │ │   (Web Search)   │
   └──────────────────┘ └──────────────────┘ └──────────────────┘
```

### Package Structure

```
invictus-ai-agent-platform/
├── apps/
│   └── agent_api/src/agent_api/
│       ├── api/
│       │   ├── routes.py      # FastAPI endpoints
│       │   └── schemas.py     # Pydantic models
│       └── main.py            # Application entry
├── packages/
│   ├── agent_core/src/agent_core/
│   │   ├── graph/
│   │   │   ├── base_graph.py  # LangGraph definition
│   │   │   └── nodes/         # Graph node functions
│   │   ├── tools/
│   │   │   ├── deals_mcp.py   # Deals domain tools
│   │   │   ├── mcp_client.py  # Generic MCP client
│   │   │   ├── rag_gateway.py # Document extraction
│   │   │   └── web_search.py  # Tavily web search
│   │   └── memory/
│   │       └── cosmos_checkpointer.py  # State persistence
│   ├── common/src/common/
│   │   ├── config.py          # Settings management
│   │   ├── logging.py         # Structured logging
│   │   └── errors.py          # Error definitions
│   └── mcp_common/src/mcp_common/
│       ├── auth.py            # Authentication
│       └── telemetry.py       # Observability
```

---

## API Endpoints

### POST `/v1/copilot/chat`

Non-streaming chat endpoint supporting both ask and agent modes.

**Request:** `UnifiedChatRequest`
**Response:** `ChatResponse`

### POST `/v1/copilot/stream`

SSE streaming endpoint with real-time "thinking" events.

**Request:** `UnifiedChatRequest`
**Response:** `EventSourceResponse` (SSE stream)

---

## Request Types

### UnifiedChatRequest

```python
{
    # Core identifiers
    "tenant_id": "string",           # Required: Tenant identifier
    "user_id": "string",             # Required: User identifier
    "module_id": "deals",            # Optional: Module (deals, crm, risk, client_portal)

    # Message content
    "message": "string",             # Required: User's message
    "additional_prompt": "string",   # Optional: Extra context (e.g., "This is for a board meeting")

    # Context
    "page_context": {                # Optional: Current page context
        "module_id": "deals",
        "screen_name": "opportunity_detail",
        "opportunity_id": "opp-123",
        "opportunity_name": "Acme Fund III",
        "screen_highlights": {},     # Module-specific data
        "additional_context": {}
    },
    "document_ids": ["doc-1", "doc-2"],  # [DEPRECATED] Use selected_docs instead
    "selected_docs": {                   # Optional: Documents with storage config for RAG
        "doc_ids": ["doc-1", "doc-2"],
        "doc_sets": [],
        "storage": {                     # Required for RAG to work
            "account_url": "https://your-storage.blob.core.windows.net",
            "filesystem": "documents",
            "base_prefix": "tenant-123/"
        }
    },

    # Session
    "session_id": "string",          # Optional: For conversational continuity

    # Request type configuration
    "type": "ask",                   # "ask" or "agent"
    "agent_case": "create",          # For agent type: "edit" or "create"

    # Agent mode specific
    "current_artifact": {            # Required for agent edit mode
        "artifact_id": "art-123",
        "artifact_type": "investment_memo",
        "title": "Acme Fund III - Investment Memo",
        "content": "# Investment Memo\n...",
        "metadata": {}
    },

    # Tool enablement
    "enabled_mcps": ["deals"],       # List of enabled MCP servers (empty [] = no MCPs)
    "web_search_enabled": false      # Enable Tavily web search
}
```

### ChatResponse

```python
{
    "session_id": "string",
    "message": "string",             # AI response text
    "tool_results": [...],           # Tool call results
    "citations": [...],              # Source citations
    "intent": "string",              # Detected intent

    # Agent mode fields
    "artifact": {                    # For agent create mode
        "artifact_id": "string",
        "artifact_type": "investment_memo",
        "title": "string",
        "content": "string",
        "version": 1,
        "citations": [...],
        "metadata": {}
    },
    "edit_instructions": [           # For agent edit mode
        {
            "operation": "modify",   # "add", "remove", "modify"
            "section_id": "executive_summary",
            "section_title": "Executive Summary",
            "position": "replace",   # "before", "after", "replace"
            "content": "New content...",
            "reasoning": "Updated based on latest data"
        }
    ]
}
```

---

## SSE Events

The streaming endpoint emits the following event types:

| Event Type | Description | Data |
|------------|-------------|------|
| `status` | Processing status updates | `{ status, session_id, type }` |
| `thinking` | Intermediate thoughts | `{ message, node }` |
| `tool_call_start` | Tool execution started | `{ tool_name, input }` |
| `tool_call_result` | Tool execution completed | `{ tool_name, success, latency_ms }` |
| `assistant_delta` | Response text chunk (ask mode) | `{ content }` |
| `artifact_update` | Generated artifact (agent create) | `{ artifact_id, content, ... }` |
| `edit_instruction` | Edit instruction (agent edit) | `{ operation, section_id, ... }` |
| `hitl_request` | Human-in-the-loop required | `{ question, options }` |
| `final` | Processing complete | `{ session_id, type, tool_call_count }` |
| `error` | Error occurred | `{ error }` |

### Example SSE Stream

```
event: status
data: {"event_type": "status", "data": {"status": "processing", "session_id": "abc-123"}}

event: thinking
data: {"event_type": "thinking", "data": {"message": "Looking up opportunity details...", "node": "gather_context"}}

event: tool_call_result
data: {"event_type": "tool_call_result", "data": {"tool_name": "deals:get_opportunity_details", "success": true, "latency_ms": 45}}

event: thinking
data: {"event_type": "thinking", "data": {"message": "Searching the web for relevant information...", "node": "gather_context"}}

event: tool_call_result
data: {"event_type": "tool_call_result", "data": {"tool_name": "tavily:web_search", "success": true, "latency_ms": 820}}

event: thinking
data: {"event_type": "thinking", "data": {"message": "Context gathered, generating response...", "node": "gather_context"}}

event: assistant_delta
data: {"event_type": "assistant_delta", "data": {"content": "Based on the opportunity data..."}}

event: final
data: {"event_type": "final", "data": {"session_id": "abc-123", "type": "ask", "tool_call_count": 3}}
```

---

## Graph Flow

### Ask Mode Flow

```
ingest_context → route_request → route_intent → gather_context → draft_or_answer → finalize → END
```

1. **ingest_context**: Validate request, normalize context, emit initial thinking event
2. **route_request**: Determine ask vs agent mode
3. **route_intent**: Classify user intent (greeting, question, command, clarification)
4. **gather_context**: Call tools (Deals MCP, RAG) to gather relevant data
5. **draft_or_answer**: Generate response using LLM with gathered context
6. **finalize**: Format final response, collect citations

### Agent Mode Flow

```
ingest_context → route_request → determine_action →
    [EDIT]:   gather_for_edit → generate_edit_instructions → finalize_agent → END
    [CREATE]: gather_for_create → generate_artifact → finalize_agent → END
```

1. **determine_action**: Route to edit or create flow based on `agent_case`
2. **gather_for_edit/create**: Gather context specific to the operation
3. **generate_edit_instructions**: Produce diff-based modifications
4. **generate_artifact**: Create new structured document
5. **finalize_agent**: Format agent-specific response

---

## Tools

### Deals MCP Tools

Mock implementations for private equity deal management:

| Tool | Description | Returns |
|------|-------------|---------|
| `get_opportunity_details` | Fetch opportunity information | name, status, target_raise, sector, etc. |
| `get_prescreening_report` | Get prescreening analysis | recommendation, risk_rating, key_findings |
| `get_investment_memo` | Retrieve existing memo | sections, version, executive_summary |
| `get_opportunity_activity` | Recent activity log | activities with date, action, user |

### RAG Gateway

Document extraction with field-based querying:

```python
# Generate fields based on question
fields = await generate_fields_for_question(
    question="What are the key risks?",
    llm=llm
)
# ["key_risks", "risk_factors", "risk_assessment"]

# Extract from documents
result = await extract_fields(
    doc_ids=["doc-1", "doc-2"],
    storage=StorageConfig(...),
    fields=fields,
    user_question="What are the key risks?"
)
```

### Tavily Web Search

Internet search for real-time information (requires `TAVILY_API_KEY`):

```python
from agent_core.tools.web_search import web_search, search_for_context

# Basic web search
result = await web_search(
    query="Private equity ESG trends 2024",
    search_depth="advanced",  # "basic" or "advanced"
    max_results=5,
    include_answer=True,      # AI-generated summary
)

# Contextual search with opportunity context
result = await search_for_context(
    user_question="What are the latest market trends?",
    opportunity_name="Acme Fund III",  # Optional
    sector="Technology",               # Optional
)

# Result structure
{
    "success": True,
    "query": "...",
    "results": [
        {
            "title": "Article Title",
            "url": "https://...",
            "content": "Snippet...",
            "score": 0.95
        }
    ],
    "answer": "AI-generated summary..."  # If include_answer=True
}
```

**Enabling Web Search:**
Set `web_search_enabled: true` in the request to enable Tavily search during context gathering.

---

## Usage Examples

### Ask Mode - Simple Question

```bash
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "tenant-123",
    "user_id": "user-456",
    "message": "What is the target raise for this opportunity?",
    "type": "ask",
    "page_context": {
      "screen_name": "opportunity_detail",
      "opportunity_id": "opp-abc"
    }
  }'
```

### Agent Mode - Create Artifact

```bash
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "tenant-123",
    "user_id": "user-456",
    "message": "Create an investment memo for this opportunity",
    "type": "agent",
    "agent_case": "create",
    "additional_prompt": "Focus on ESG factors",
    "page_context": {
      "screen_name": "opportunity_detail",
      "opportunity_id": "opp-abc",
      "opportunity_name": "Acme Fund III"
    },
    "enabled_mcps": ["deals"]
  }'
```

### Agent Mode - Edit Artifact

```bash
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "tenant-123",
    "user_id": "user-456",
    "message": "Add a section about ESG considerations",
    "type": "agent",
    "agent_case": "edit",
    "current_artifact": {
      "artifact_id": "art-123",
      "artifact_type": "investment_memo",
      "title": "Acme Fund III - Investment Memo",
      "content": "# Investment Memo\n\n## Executive Summary\n..."
    }
  }'
```

### Ask Mode with Web Search

```bash
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "tenant-123",
    "user_id": "user-456",
    "message": "What are the latest market trends in private equity?",
    "type": "ask",
    "web_search_enabled": true,
    "page_context": {
      "screen_name": "dashboard",
      "opportunity_id": "opp-abc"
    }
  }'
```

### SSE Streaming

```javascript
const eventSource = new EventSource('/v1/copilot/stream', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    tenant_id: 'tenant-123',
    user_id: 'user-456',
    message: 'Tell me about this opportunity',
    type: 'ask',
    page_context: {
      opportunity_id: 'opp-abc'
    }
  })
});

eventSource.addEventListener('thinking', (e) => {
  const data = JSON.parse(e.data);
  console.log('Thinking:', data.data.message);
});

eventSource.addEventListener('assistant_delta', (e) => {
  const data = JSON.parse(e.data);
  appendToResponse(data.data.content);
});

eventSource.addEventListener('final', (e) => {
  eventSource.close();
});
```

---

## Configuration

Environment variables (see `.env`):

```env
# Environment
ENVIRONMENT=development
LOG_LEVEL=INFO

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
AZURE_OPENAI_API_VERSION=2024-02-01

# Cosmos DB (State Persistence)
COSMOS_ENDPOINT=https://your-cosmos.documents.azure.com:443/
COSMOS_KEY=your-cosmos-key
COSMOS_DATABASE_NAME=invictus-copilot
COSMOS_SESSIONS_CONTAINER=sessions
COSMOS_CHECKPOINTS_CONTAINER=checkpoints
COSMOS_ARTIFACTS_CONTAINER=artifacts

# RAG Gateway
RAG_GATEWAY_URL=https://your-rag-gateway.com
RAG_GATEWAY_API_KEY=your-rag-key

# MCP Server URLs (for future integration)
MCP_OPPORTUNITIES_URL=http://localhost:8001
MCP_CLIENTS_URL=http://localhost:8002
MCP_RISK_PLANNING_URL=http://localhost:8003
MCP_REPORTING_URL=http://localhost:8004
MCP_ADMIN_POLICY_URL=http://localhost:8005

# Optional
TAVILY_API_KEY=your-tavily-key  # For web search
```

---

## Running the Application

```bash
# Install dependencies
pip install -e apps/agent_api
pip install -e packages/agent_core
pip install -e packages/common
pip install -e packages/mcp_common

# Set environment variables
export PYTHONPATH="apps/agent_api/src:packages/agent_core/src:packages/common/src:packages/mcp_common/src"

# Run the API
uvicorn agent_api.main:app --reload --port 8000
```

---

## State Persistence

The agent uses Cosmos DB for state persistence via LangGraph's checkpointer:

- **Sessions**: Conversation history and context
- **Checkpoints**: Graph state snapshots for resumption
- **Artifacts**: Generated documents with versioning

If Cosmos DB is unavailable, the agent runs without persistence (in-memory only).

---

## Error Handling

Errors are returned in a consistent format:

```python
{
    "error": "Error type or message",
    "detail": "Detailed error description",
    "request_id": "optional-request-id"
}
```

For SSE streams, errors are emitted as `error` events before the stream closes.
