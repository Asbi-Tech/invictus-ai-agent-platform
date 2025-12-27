# Invictus Copilot API (Multi-Agent)

A LangGraph-based multi-agent platform with mandatory Human-in-the-Loop (HITL) gates, parallel section writing, and comprehensive source attribution.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [API Endpoints](#api-endpoints)
- [Request Types](#request-types)
- [SSE Events](#sse-events)
- [Multi-Agent Flow](#multi-agent-flow)
- [HITL Protocol](#hitl-protocol)
- [Tools](#tools)
- [Usage Examples](#usage-examples)
- [Configuration](#configuration)

---

## Overview

The Copilot API is a multi-agent system with 10 specialized subgraphs orchestrated by a central coordinator. It supports:

| Mode | Purpose | Output |
|------|---------|--------|
| **Ask** | Conversational Q&A with RAG and tool access | Text response with citations |
| **Agent (Create)** | Generate new documents/artifacts | Structured artifact (memo, report, etc.) |
| **Agent (Edit)** | Modify existing artifacts | Diff-based edit instructions |

### Key Features

- **Mandatory HITL Gates**: Clarification and plan confirmation before execution
- **10 Specialized Subgraphs**: Intent analysis, planning, data retrieval, synthesis, section writing, review
- **Parallel Section Writing**: Concurrent generation of document sections
- **Section-Level Source Attribution**: Every section linked to its data sources
- **Rich SSE Streaming**: 25+ event types for real-time UI updates

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         FastAPI Router                                   │
│              /v1/copilot/chat, /stream, /stream/resume                  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Multi-Agent Orchestrator                              │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                        Subgraphs                                  │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐            │   │
│  │  │ Intent   │ │Clarifi-  │ │ Planning │ │Confirma- │            │   │
│  │  │ Analyzer │ │ cation   │ │          │ │  tion    │            │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘            │   │
│  │       │            │            │            │                    │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐            │   │
│  │  │  Data    │ │Synthesis │ │ Template │ │ Section  │            │   │
│  │  │Retrieval │ │          │ │ Manager  │ │ Writers  │            │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘            │   │
│  │       │                                       │                    │   │
│  │  ┌──────────┐                          ┌──────────┐              │   │
│  │  │  Review  │                          │ Source   │              │   │
│  │  │          │                          │ Mapper   │              │   │
│  │  └──────────┘                          └──────────┘              │   │
│  └──────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
              ┌─────────────────────┼─────────────────────┐
              ▼                     ▼                     ▼
   ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
   │   Deals MCP      │  │   RAG Gateway    │  │   Tavily         │
   │   (Structured)   │  │   (Documents)    │  │   (Web Search)   │
   └──────────────────┘  └──────────────────┘  └──────────────────┘
```

### Package Structure

```
invictus-ai-agent-platform/
├── apps/
│   └── agent_api/src/agent_api/
│       ├── api/
│       │   ├── routes.py         # FastAPI endpoints + HITL handling
│       │   └── schemas.py        # Pydantic models + SSE events
│       └── main.py               # Application entry
├── packages/
│   ├── agent_core/src/agent_core/
│   │   ├── graph/
│   │   │   ├── base_graph.py     # Multi-agent orchestrator
│   │   │   ├── state.py          # MultiAgentState schema
│   │   │   └── subgraphs/        # 10 specialized subgraphs
│   │   │       ├── intent_analyzer/
│   │   │       ├── clarification/
│   │   │       ├── planning/
│   │   │       ├── confirmation/
│   │   │       ├── data_retrieval/
│   │   │       ├── synthesis/
│   │   │       ├── template_manager/
│   │   │       ├── section_writer/
│   │   │       ├── review/
│   │   │       └── source_mapper/
│   │   ├── tools/
│   │   │   ├── deals_mcp.py      # Deals domain tools
│   │   │   ├── rag_gateway.py    # Document extraction
│   │   │   └── web_search.py     # Tavily web search
│   │   └── memory/
│   │       └── cosmos_checkpointer.py  # State persistence
│   ├── common/src/common/
│   │   ├── config.py             # Settings management
│   │   └── logging.py            # Structured logging
│   └── mcp_common/src/mcp_common/
│       └── auth.py               # Authentication
```

---

## API Endpoints

### POST `/v1/copilot/chat`

Non-streaming chat endpoint supporting both ask and agent modes.

**Request:** `UnifiedChatRequest`
**Response:** `ChatResponse`

### POST `/v1/copilot/stream`

SSE streaming endpoint with real-time events and HITL support.

**Request:** `UnifiedChatRequest`
**Response:** `EventSourceResponse` (SSE stream)

When the graph pauses for HITL (clarification or confirmation), emits a `status: paused` event with `resume_endpoint`.

### POST `/v1/copilot/stream/resume`

Resume a paused execution with user input.

**Request:** `ResumeRequest`
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
    "additional_prompt": "string",   # Optional: Extra context

    # Context
    "page_context": {                # Optional: Current page context
        "module_id": "deals",
        "screen_name": "opportunity_detail",
        "opportunity_id": "opp-123",
        "opportunity_name": "Acme Fund III",
        "screen_highlights": {},
        "additional_context": {}
    },
    "selected_docs": {               # Optional: Documents for RAG
        "doc_ids": ["doc-1", "doc-2"],
        "doc_sets": [],
        "storage": {
            "account_url": "https://your-storage.blob.core.windows.net",
            "filesystem": "documents",
            "base_prefix": "tenant-123/"
        }
    },

    # Session
    "session_id": "string",          # Optional: For conversational continuity

    # Request type
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
    "enabled_mcps": ["deals"],       # List of enabled MCP servers
    "web_search_enabled": false      # Enable web search
}
```

### ResumeRequest

```python
{
    "session_id": "string",          # Required: Session ID of paused execution

    # For clarification responses
    "clarification_response": {      # Optional: Answers to clarification questions
        "question_id_1": "answer_1",
        "question_id_2": "answer_2"
    },

    # For plan confirmation
    "confirmation_response": "approved",  # "approved", "modify", or "cancelled"
    "plan_modifications": ["..."]    # Optional: Requested changes if "modify"
}
```

### ChatResponse

```python
{
    "session_id": "string",
    "message": "string",
    "tool_results": [...],
    "citations": [...],
    "intent": "string",

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
    "edit_instructions": [...]       # For agent edit mode
}
```

---

## SSE Events

The streaming endpoints emit the following event types:

### Connection & Status Events

| Event Type | Description | Data |
|------------|-------------|------|
| `status` | Processing status | `{ status, session_id, type }` |
| `thinking` | Intermediate thoughts | `{ message, node }` |
| `final` | Processing complete | `{ session_id, type, tool_call_count, current_phase }` |
| `error` | Error occurred | `{ error }` |

### HITL Events

| Event Type | Description | Data |
|------------|-------------|------|
| `clarification_required` | User input needed | `{ session_id, questions, message }` |
| `clarification_resolved` | Clarification received | `{ session_id, responses }` |
| `plan_generated` | Execution plan created | `{ plan_id, sections, data_requirements }` |
| `awaiting_confirmation` | Plan approval needed | `{ session_id, plan, message }` |
| `confirmation_received` | User confirmed/modified/cancelled | `{ session_id, response }` |

### Phase Lifecycle Events

| Event Type | Description | Data |
|------------|-------------|------|
| `phase_started` | Phase began | `{ phase, message }` |
| `phase_completed` | Phase finished | `{ phase, ... }` |
| `intent_detected` | Intent classified | `{ request_type, document_type }` |
| `entities_detected` | Entities found | `{ entities }` |

### Data Retrieval Events

| Event Type | Description | Data |
|------------|-------------|------|
| `fetching_mcp_data` | MCP query started | `{ domain }` |
| `mcp_data_received` | MCP data received | `{ domain, data_keys }` |
| `fetching_rag_data` | RAG query started | `{ doc_count }` |
| `rag_data_received` | RAG data received | `{ fields_extracted }` |
| `fetching_web_data` | Web search started | `{ query }` |
| `web_data_received` | Web results received | `{ result_count }` |

### Synthesis Events

| Event Type | Description | Data |
|------------|-------------|------|
| `synthesis_started` | Data synthesis began | `{ message }` |
| `insight_generated` | Insight extracted | `{ insight }` |
| `synthesis_completed` | Synthesis finished | `{ insights_count }` |

### Template Events

| Event Type | Description | Data |
|------------|-------------|------|
| `template_selected` | Template chosen | `{ template_id, section_count }` |
| `template_adapted` | Template modified | `{ adaptations }` |

### Section Generation Events

| Event Type | Description | Data |
|------------|-------------|------|
| `section_started` | Section writing began | `{ section_id, section_name }` |
| `section_progress` | Section progress update | `{ section_id, progress }` |
| `section_completed` | Section finished | `{ section_id, word_count }` |

### Review Events

| Event Type | Description | Data |
|------------|-------------|------|
| `review_started` | Quality review began | `{ message }` |
| `review_issue_found` | Issue detected | `{ issue_type, severity, description }` |
| `review_completed` | Review finished | `{ coherence_score, issues_count, approved }` |

### Source Attribution Events

| Event Type | Description | Data |
|------------|-------------|------|
| `source_mapped` | Sources linked to sections | `{ total_sources, sections_mapped }` |

### Response Streaming Events

| Event Type | Description | Data |
|------------|-------------|------|
| `tool_call_start` | Tool execution started | `{ tool_name, input }` |
| `tool_call_result` | Tool execution completed | `{ tool_name, success, latency_ms }` |
| `assistant_delta` | Response text chunk | `{ content }` |
| `artifact_update` | Generated artifact | `{ artifact_id, content, ... }` |
| `edit_instruction` | Edit instruction | `{ operation, section_id, ... }` |

---

## Multi-Agent Flow

### Complete Agent Flow

```
                    ┌──────────────────┐
                    │  ingest_context  │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │ intent_analyzer  │  ← Classify request, detect entities
                    └────────┬─────────┘
                             │
              ┌──────────────┴──────────────┐
              │                             │
    [clarification needed]          [ready to plan]
              │                             │
    ┌─────────▼─────────┐                   │
    │   clarification   │  ← HITL INTERRUPT │
    └─────────┬─────────┘                   │
              │                             │
              └──────────────┬──────────────┘
                             │
                    ┌────────▼─────────┐
                    │     planning     │  ← Generate execution plan
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │confirmation_gate │  ← HITL INTERRUPT
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
         [approved]     [modify]      [cancelled]
              │              │              │
              │         (loop to           END
              │          planning)
              │
     ┌────────▼─────────┐
     │  data_retrieval  │  ← MCP + RAG + Web agents
     └────────┬─────────┘
              │
     ┌────────▼─────────┐
     │    synthesis     │  ← Normalize, insights, confidence
     └────────┬─────────┘
              │
     ┌────────▼─────────┐
     │ template_manager │  ← Select and map template
     └────────┬─────────┘
              │
     ┌────────▼─────────┐
     │ section_writers  │  ← PARALLEL section generation
     └────────┬─────────┘
              │
     ┌────────▼─────────┐
     │     review       │  ← Coherence, citations, suggestions
     └────────┬─────────┘
              │
     ┌────────▼─────────┐
     │  source_mapper   │  ← Build source ledger
     └────────┬─────────┘
              │
     ┌────────▼─────────┐
     │    finalize      │
     └────────┬─────────┘
              │
             END
```

### Subgraph Descriptions

| Subgraph | Purpose |
|----------|---------|
| **intent_analyzer** | Classifies request type, detects document type, identifies entities |
| **clarification** | Generates and collects clarification questions (HITL interrupt) |
| **planning** | Creates execution plan with sections, data requirements, tool usage |
| **confirmation** | Presents plan for user approval (HITL interrupt) |
| **data_retrieval** | Orchestrates MCP, RAG, and Web data collection |
| **synthesis** | Normalizes data, generates insights, scores confidence |
| **template_manager** | Selects template, maps sections to data sources |
| **section_writer** | Writes all sections in parallel using asyncio.gather |
| **review** | Checks coherence, validates citations, generates suggestions |
| **source_mapper** | Builds source ledger, links sections to sources |

---

## HITL Protocol

The system has two mandatory HITL gates that pause execution and wait for user input.

### Clarification Flow

When the system needs more information:

1. **System emits** `clarification_required` event:
```json
{
  "event_type": "clarification_required",
  "data": {
    "session_id": "abc-123",
    "questions": [
      {
        "question_id": "q1",
        "question": "Which opportunity should I create the memo for?",
        "options": ["Acme Fund III", "Beta Capital II"],
        "required": true
      }
    ],
    "message": "Please provide additional information to continue."
  }
}
```

2. **System emits** `status: paused`:
```json
{
  "event_type": "status",
  "data": {
    "status": "paused",
    "session_id": "abc-123",
    "interrupt_type": "clarification",
    "resume_endpoint": "/v1/copilot/stream/resume"
  }
}
```

3. **User calls** `/stream/resume`:
```json
{
  "session_id": "abc-123",
  "clarification_response": {
    "q1": "Acme Fund III"
  }
}
```

4. **System resumes** and emits `clarification_resolved`

### Confirmation Flow

When the execution plan is ready:

1. **System emits** `awaiting_confirmation` event:
```json
{
  "event_type": "awaiting_confirmation",
  "data": {
    "session_id": "abc-123",
    "plan": {
      "plan_id": "plan-456",
      "sections": [
        {"id": "exec_summary", "name": "Executive Summary"},
        {"id": "investment_thesis", "name": "Investment Thesis"}
      ],
      "data_requirements": [
        {"source": "mcp:deals", "query": "opportunity_details"}
      ],
      "template_strategy": "use_existing"
    },
    "message": "Please review and approve the execution plan."
  }
}
```

2. **System emits** `status: paused`

3. **User calls** `/stream/resume`:
```json
{
  "session_id": "abc-123",
  "confirmation_response": "approved"
}
```

Or to modify:
```json
{
  "session_id": "abc-123",
  "confirmation_response": "modify",
  "plan_modifications": ["Add ESG section", "Focus more on risks"]
}
```

4. **System resumes** (or loops back to planning if "modify")

---

## Tools

### Deals MCP Tools

Structured data from the deals domain:

| Tool | Description | Returns |
|------|-------------|---------|
| `get_opportunity_details` | Fetch opportunity information | name, status, target_raise, sector |
| `get_prescreening_report` | Get prescreening analysis | recommendation, risk_rating, key_findings |
| `get_investment_memo` | Retrieve existing memo | sections, version, executive_summary |
| `get_opportunity_activity` | Recent activity log | activities with date, action, user |

### RAG Gateway

Document extraction with field-based querying:

```python
result = await extract_fields(
    doc_ids=["doc-1", "doc-2"],
    storage=StorageConfig(...),
    fields=["key_risks", "financials"],
    user_question="What are the key risks?"
)
```

### Tavily Web Search

Internet search for real-time information:

```python
result = await web_search(
    query="Private equity ESG trends 2024",
    search_depth="advanced",
    max_results=5,
    include_answer=True
)
```

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

### Agent Mode - Create Artifact (with HITL)

```javascript
// Start the stream
const eventSource = new EventSource('/v1/copilot/stream', {
  method: 'POST',
  body: JSON.stringify({
    tenant_id: 'tenant-123',
    user_id: 'user-456',
    message: 'Create an investment memo for this opportunity',
    type: 'agent',
    agent_case: 'create',
    page_context: {
      opportunity_id: 'opp-abc',
      opportunity_name: 'Acme Fund III'
    }
  })
});

// Handle HITL pause
eventSource.addEventListener('awaiting_confirmation', (e) => {
  const data = JSON.parse(e.data);
  showPlanApprovalDialog(data.data.plan);
});

eventSource.addEventListener('status', (e) => {
  const data = JSON.parse(e.data);
  if (data.data.status === 'paused') {
    // Wait for user to approve/modify/cancel
  }
});
```

### Resume After Confirmation

```javascript
// After user approves the plan
const resumeSource = new EventSource('/v1/copilot/stream/resume', {
  method: 'POST',
  body: JSON.stringify({
    session_id: 'abc-123',
    confirmation_response: 'approved'
  })
});

resumeSource.addEventListener('section_completed', (e) => {
  const data = JSON.parse(e.data);
  console.log(`Section ${data.data.section_id} complete`);
});

resumeSource.addEventListener('artifact_update', (e) => {
  const data = JSON.parse(e.data);
  displayArtifact(data.data);
});
```

### Example SSE Stream (Full Flow)

```
event: status
data: {"event_type": "status", "data": {"status": "processing", "session_id": "abc-123"}}

event: phase_started
data: {"event_type": "phase_started", "data": {"phase": "intent", "message": "Analyzing request..."}}

event: intent_detected
data: {"event_type": "intent_detected", "data": {"request_type": "create", "document_type": "investment_memo"}}

event: phase_started
data: {"event_type": "phase_started", "data": {"phase": "planning", "message": "Creating execution plan..."}}

event: plan_generated
data: {"event_type": "plan_generated", "data": {"plan_id": "plan-456", "sections": [...]}}

event: awaiting_confirmation
data: {"event_type": "awaiting_confirmation", "data": {"session_id": "abc-123", "plan": {...}}}

event: status
data: {"event_type": "status", "data": {"status": "paused", "interrupt_type": "confirmation"}}

... (user resumes with approval) ...

event: status
data: {"event_type": "status", "data": {"status": "resuming", "session_id": "abc-123"}}

event: fetching_mcp_data
data: {"event_type": "fetching_mcp_data", "data": {"domain": "deals"}}

event: mcp_data_received
data: {"event_type": "mcp_data_received", "data": {"domain": "deals", "data_keys": ["opportunity", "prescreening"]}}

event: section_started
data: {"event_type": "section_started", "data": {"section_id": "exec_summary", "section_name": "Executive Summary"}}

event: section_completed
data: {"event_type": "section_completed", "data": {"section_id": "exec_summary", "word_count": 250}}

event: review_completed
data: {"event_type": "review_completed", "data": {"coherence_score": 0.92, "issues_count": 1, "approved": true}}

event: artifact_update
data: {"event_type": "artifact_update", "data": {"artifact_id": "art-789", "title": "Acme Fund III - Investment Memo", "content": "..."}}

event: final
data: {"event_type": "final", "data": {"session_id": "abc-123", "type": "agent", "artifact_count": 1}}
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

# Cosmos DB (State Persistence for HITL)
COSMOS_ENDPOINT=https://your-cosmos.documents.azure.com:443/
COSMOS_KEY=your-cosmos-key
COSMOS_DATABASE_NAME=invictus-copilot
COSMOS_SESSIONS_CONTAINER=sessions
COSMOS_CHECKPOINTS_CONTAINER=checkpoints
COSMOS_ARTIFACTS_CONTAINER=artifacts

# RAG Gateway
RAG_GATEWAY_URL=https://your-rag-gateway.com
RAG_GATEWAY_API_KEY=your-rag-key

# MCP Server URLs
MCP_OPPORTUNITIES_URL=http://localhost:8001
MCP_CLIENTS_URL=http://localhost:8002
MCP_RISK_PLANNING_URL=http://localhost:8003

# Optional
TAVILY_API_KEY=your-tavily-key
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

The agent uses Cosmos DB for state persistence, which is **required** for HITL to work:

- **Sessions**: Conversation history and context
- **Checkpoints**: Graph state snapshots for HITL resume
- **Artifacts**: Generated documents with versioning

If Cosmos DB is unavailable, HITL functionality will not work (sessions cannot be resumed).

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
