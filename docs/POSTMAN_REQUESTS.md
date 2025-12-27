# Invictus Copilot API - Postman Requests

This document contains all API request examples for testing the Copilot API endpoints using Postman or cURL.

## Base URL

```
http://localhost:8000
```

---

## Table of Contents

- [1. Non-Streaming Endpoint (`/v1/copilot/chat`)](#1-non-streaming-endpoint-v1copilotchat)
  - [1.1 Ask Mode - Simple Question](#11-ask-mode---simple-question)
  - [1.2 Ask Mode - With Page Context](#12-ask-mode---with-page-context)
  - [1.3 Ask Mode - With Document Selection (RAG)](#13-ask-mode---with-document-selection-rag)
  - [1.4 Ask Mode - With Web Search](#14-ask-mode---with-web-search)
  - [1.5 Ask Mode - Multi-turn Conversation](#15-ask-mode---multi-turn-conversation)
  - [1.6 Agent Create Mode - Investment Memo](#16-agent-create-mode---investment-memo)
  - [1.7 Agent Create Mode - Prescreening Report](#17-agent-create-mode---prescreening-report)
  - [1.8 Agent Edit Mode - Edit Existing Artifact](#18-agent-edit-mode---edit-existing-artifact)
- [2. Streaming Endpoint (`/v1/copilot/stream`)](#2-streaming-endpoint-v1copilotstream)
  - [2.1 Stream - Ask Mode](#21-stream---ask-mode)
  - [2.2 Stream - Agent Create Mode](#22-stream---agent-create-mode)
  - [2.3 Stream - Agent Edit Mode](#23-stream---agent-edit-mode)
- [3. Resume Endpoint (`/v1/copilot/stream/resume`)](#3-resume-endpoint-v1copilotstreamresume)
  - [3.1 Resume - Clarification Response](#31-resume---clarification-response)
  - [3.2 Resume - Plan Approved](#32-resume---plan-approved)
  - [3.3 Resume - Plan Modify](#33-resume---plan-modify)
  - [3.4 Resume - Plan Cancelled](#34-resume---plan-cancelled)
- [4. Error Scenarios](#4-error-scenarios)

---

## 1. Non-Streaming Endpoint (`/v1/copilot/chat`)

### 1.1 Ask Mode - Simple Question

Minimal payload for a simple Q&A request.

```bash
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "tenant-123",
    "user_id": "user-456",
    "message": "What is the target raise for this opportunity?",
    "type": "ask"
  }'
```

**Postman Body (JSON):**
```json
{
    "tenant_id": "tenant-123",
    "user_id": "user-456",
    "message": "What is the target raise for this opportunity?",
    "type": "ask"
}
```

---

### 1.2 Ask Mode - With Page Context

Include current page context for opportunity-specific queries.

```bash
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "tenant-123",
    "user_id": "user-456",
    "message": "What is the risk rating for this deal?",
    "type": "ask",
    "module_id": "deals",
    "page_context": {
        "module_id": "deals",
        "screen_name": "opportunity_detail",
        "opportunity_id": "opp-001",
        "opportunity_name": "Acme Fund III",
        "screen_highlights": {
            "sector": "Technology",
            "stage": "Series B"
        },
        "additional_context": {
            "last_updated": "2024-12-01"
        }
    },
    "enabled_mcps": ["deals"]
  }'
```

**Postman Body (JSON):**
```json
{
    "tenant_id": "tenant-123",
    "user_id": "user-456",
    "message": "What is the risk rating for this deal?",
    "type": "ask",
    "module_id": "deals",
    "page_context": {
        "module_id": "deals",
        "screen_name": "opportunity_detail",
        "opportunity_id": "opp-001",
        "opportunity_name": "Wonder Group Inc",
        "screen_highlights": {
            "sector": "Food Technology",
            "stage": "SAFE Note"
        },
        "additional_context": {
            "last_updated": "2024-12-01"
        }
    },
    "enabled_mcps": ["deals"]
}
```

---

### 1.3 Ask Mode - With Document Selection (RAG)

Query with selected documents for RAG-based extraction.

```bash
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "raoof-copilot-test-woner",
    "user_id": "user-456",
    "message": "Summarize the key risks mentioned in the attached documents",
    "type": "ask",
    "selected_docs": {
        "doc_ids": ["c75e341a-2953-4672-b85b-6c9b4583b0da", "a6077903-0d41-4a16-8131-4442bf4d0046", "cd5774d3-407d-46ce-9818-0e069e705dd7", "ff6c110e-d323-47c8-a472-7bfa5f1a257a"],
        "doc_sets": ["due_diligence"],
        "storage": {
            "account_url": "https://stinvictusuaenorthdev.blob.core.windows.net",
            "filesystem": "documents",
            "base_prefix": "tenants/raoof-copilot-test-woner/modules/invictus-deals/use-cases/test-01/pre-screening-report/documents/"
        }
    }
  }'
```

**Postman Body (JSON):**
```json
{
    "tenant_id": "raoof-copilot-test-woner",
    "user_id": "user-456",
    "message": "Summarize the key risks mentioned in the attached documents",
    "type": "ask",
    "selected_docs": {
        "doc_ids": ["c75e341a-2953-4672-b85b-6c9b4583b0da", "a6077903-0d41-4a16-8131-4442bf4d0046", "cd5774d3-407d-46ce-9818-0e069e705dd7", "ff6c110e-d323-47c8-a472-7bfa5f1a257a"],
        "doc_sets": ["due_diligence"],
        "storage": {
            "account_url": "https://stinvictusuaenorthdev.blob.core.windows.net",
            "filesystem": "documents",
            "base_prefix": "tenants/raoof-copilot-test-woner/modules/invictus-deals/use-cases/test-01/pre-screening-report/documents/"
        }
    }
}
```

---

### 1.4 Ask Mode - With Web Search

Enable web search for real-time information.

```bash
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "tenant-123",
    "user_id": "user-456",
    "message": "What are the latest ESG trends in private equity for 2024?",
    "type": "ask",
    "web_search_enabled": true
  }'
```

**Postman Body (JSON):**
```json
{
    "tenant_id": "tenant-123",
    "user_id": "user-456",
    "message": "What are the latest ESG trends in private equity for 2024?",
    "type": "ask",
    "web_search_enabled": true
}
```

---

### 1.5 Ask Mode - Multi-turn Conversation

Continue a conversation with session_id.

**First message (no session_id):**
```bash
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "tenant-123",
    "user_id": "user-456",
    "message": "Tell me about the Wonder Group Inc opportunity",
    "type": "ask",
    "page_context": {
        "screen_name": "opportunity_detail",
        "opportunity_id": "opp-001"
    }
  }'
```

**Follow-up message (with session_id from response):**
```bash
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "tenant-123",
    "user_id": "user-456",
    "message": "What are the main risks?",
    "type": "ask",
    "session_id": "session-abc-123-from-previous-response"
  }'
```

**Postman Body (JSON) - Follow-up:**
```json
{
    "tenant_id": "tenant-123",
    "user_id": "user-456",
    "message": "What are the main risks?",
    "type": "ask",
    "session_id": "session-abc-123-from-previous-response"
}
```

---

### 1.6 Agent Create Mode - Investment Memo

Create a new investment memo artifact.

```bash
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "tenant-123",
    "user_id": "user-456",
    "message": "Create an investment memo for this opportunity",
    "type": "agent",
    "agent_case": "create",
    "module_id": "deals",
    "page_context": {
        "module_id": "deals",
        "screen_name": "opportunity_detail",
        "opportunity_id": "opp-001",
        "opportunity_name": "Wonder Group Inc"
    },
    "enabled_mcps": ["deals"],
    "additional_prompt": "Focus on the food technology sector and their vertically integrated model"
  }'
```

**Postman Body (JSON):**
```json
{
    "tenant_id": "tenant-123",
    "user_id": "user-456",
    "message": "Create an investment memo for this opportunity",
    "type": "agent",
    "agent_case": "create",
    "module_id": "deals",
    "page_context": {
        "module_id": "deals",
        "screen_name": "opportunity_detail",
        "opportunity_id": "opp-001",
        "opportunity_name": "Acme Fund III"
    },
    "enabled_mcps": ["deals"],
    "additional_prompt": "Focus on the food technology sector and their vertically integrated model"
}
```

---

### 1.7 Agent Create Mode - Prescreening Report

Create a prescreening report with document references.

```bash
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "raoof-copilot-test-woner",
    "user_id": "user-456",
    "message": "Generate a prescreening report for this deal",
    "type": "agent",
    "agent_case": "create",
    "page_context": {
        "screen_name": "opportunity_detail",
        "opportunity_id": "test-01",
        "opportunity_name": "Test Opportunity 01"
    },
    "selected_docs": {
        "doc_ids": ["c75e341a-2953-4672-b85b-6c9b4583b0da", "a6077903-0d41-4a16-8131-4442bf4d0046", "cd5774d3-407d-46ce-9818-0e069e705dd7", "ff6c110e-d323-47c8-a472-7bfa5f1a257a"],
        "storage": {
            "account_url": "https://stinvictusuaenorthdev.blob.core.windows.net",
            "filesystem": "documents",
            "base_prefix": "tenants/raoof-copilot-test-woner/modules/invictus-deals/use-cases/test-01/pre-screening-report/documents/"
        }
    },
    "enabled_mcps": ["deals"]
  }'
```

**Postman Body (JSON):**
```json
{
    "tenant_id": "raoof-copilot-test-woner",
    "user_id": "user-456",
    "message": "Generate a prescreening report for this deal",
    "type": "agent",
    "agent_case": "create",
    "page_context": {
        "screen_name": "opportunity_detail",
        "opportunity_id": "test-01",
        "opportunity_name": "Test Opportunity 01"
    },
    "selected_docs": {
        "doc_ids": ["c75e341a-2953-4672-b85b-6c9b4583b0da", "a6077903-0d41-4a16-8131-4442bf4d0046", "cd5774d3-407d-46ce-9818-0e069e705dd7", "ff6c110e-d323-47c8-a472-7bfa5f1a257a"],
        "storage": {
            "account_url": "https://stinvictusuaenorthdev.blob.core.windows.net",
            "filesystem": "documents",
            "base_prefix": "tenants/raoof-copilot-test-woner/modules/invictus-deals/use-cases/test-01/pre-screening-report/documents/"
        }
    },
    "enabled_mcps": ["deals"]
}
```

---

### 1.8 Agent Edit Mode - Edit Existing Artifact

Modify an existing document artifact.

```bash
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "tenant-123",
    "user_id": "user-456",
    "message": "Add a competitive analysis section and update the risk section with the latest data",
    "type": "agent",
    "agent_case": "edit",
    "current_artifact": {
        "artifact_id": "art-memo-001",
        "artifact_type": "investment_memo",
        "title": "Wonder Group Inc - Investment Memo",
        "content": "# Investment Memo\n\n## Executive Summary\nWonder Group Inc is a food-technology company building the first fully vertically integrated food delivery platform...\n\n## Investment Thesis\nWonder controls the entire value chain from restaurants to delivery, with proprietary FLASH technology enabling 40 cuisines from 3,000 sq ft locations...\n\n## Key Risks\n- Execution risk on HDR expansion\n- Competition from established aggregators\n- Capital intensity of vertical integration\n\n## Financial Overview\n| Metric | Value |\n|--------|-------|\n| GOV ARR (2023) | $407M |\n| Target GOV ARR (2027) | $4.2B+ |\n| Structure | SAFE Note - 40% IRR |",
        "metadata": {
            "version": 1,
            "created_at": "2024-12-01T10:00:00Z"
        }
    },
    "page_context": {
        "screen_name": "artifact_editor",
        "opportunity_id": "opp-001"
    },
    "enabled_mcps": ["deals"]
  }'
```

**Postman Body (JSON):**
```json
{
    "tenant_id": "tenant-123",
    "user_id": "user-456",
    "message": "Add a competitive analysis section and update the risk section with the latest data",
    "type": "agent",
    "agent_case": "edit",
    "current_artifact": {
        "artifact_id": "art-memo-001",
        "artifact_type": "investment_memo",
        "title": "Wonder Group Inc - Investment Memo",
        "content": "# Investment Memo\n\n## Executive Summary\nWonder Group Inc is a food-technology company building the first fully vertically integrated food delivery platform...\n\n## Investment Thesis\nWonder controls the entire value chain from restaurants to delivery, with proprietary FLASH technology enabling 40 cuisines from 3,000 sq ft locations...\n\n## Key Risks\n- Execution risk on HDR expansion\n- Competition from established aggregators\n- Capital intensity of vertical integration\n\n## Financial Overview\n| Metric | Value |\n|--------|-------|\n| GOV ARR (2023) | $407M |\n| Target GOV ARR (2027) | $4.2B+ |\n| Structure | SAFE Note - 40% IRR |",
        "metadata": {
            "version": 1,
            "created_at": "2024-12-01T10:00:00Z"
        }
    },
    "page_context": {
        "screen_name": "artifact_editor",
        "opportunity_id": "opp-001"
    },
    "enabled_mcps": ["deals"]
}
```

---

## 2. Streaming Endpoint (`/v1/copilot/stream`)

The streaming endpoint returns Server-Sent Events (SSE). Use appropriate SSE client or cURL with streaming.

### 2.1 Stream - Ask Mode

```bash
curl -X POST http://localhost:8000/v1/copilot/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "tenant_id": "tenant-123",
    "user_id": "user-456",
    "message": "What is the investment thesis for this opportunity?",
    "type": "ask",
    "page_context": {
        "screen_name": "opportunity_detail",
        "opportunity_id": "opp-001"
    },
    "enabled_mcps": ["deals"]
  }'
```

**Postman Body (JSON):**
```json
{
    "tenant_id": "tenant-123",
    "user_id": "user-456",
    "message": "What is the investment thesis for this opportunity?",
    "type": "ask",
    "page_context": {
        "screen_name": "opportunity_detail",
        "opportunity_id": "opp-001"
    },
    "enabled_mcps": ["deals"]
}
```

**Expected SSE Events:**
```
event: status
data: {"event_type": "status", "data": {"status": "processing", "session_id": "sess-123"}}

event: thinking
data: {"event_type": "thinking", "data": {"message": "Analyzing request..."}}

event: tool_call_start
data: {"event_type": "tool_call_start", "data": {"tool_name": "get_opportunity_details"}}

event: tool_call_result
data: {"event_type": "tool_call_result", "data": {"tool_name": "get_opportunity_details", "success": true}}

event: assistant_delta
data: {"event_type": "assistant_delta", "data": {"content": "The investment thesis for..."}}

event: final
data: {"event_type": "final", "data": {"session_id": "sess-123", "type": "ask"}}
```

---

### 2.2 Stream - Agent Create Mode

This will trigger HITL gates (clarification and confirmation).

```bash
curl -X POST http://localhost:8000/v1/copilot/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "tenant_id": "tenant-123",
    "user_id": "user-456",
    "message": "Create an investment memo for this opportunity",
    "type": "agent",
    "agent_case": "create",
    "page_context": {
        "module_id": "deals",
        "screen_name": "opportunity_detail",
        "opportunity_id": "opp-001",
        "opportunity_name": "Wonder Group Inc"
    },
    "enabled_mcps": ["deals"]
  }'
```

**Postman Body (JSON):**
```json
{
    "tenant_id": "tenant-123",
    "user_id": "user-456",
    "message": "Create an investment memo for this opportunity",
    "type": "agent",
    "agent_case": "create",
    "page_context": {
        "module_id": "deals",
        "screen_name": "opportunity_detail",
        "opportunity_id": "opp-001",
        "opportunity_name": "Wonder Group Inc"
    },
    "enabled_mcps": ["deals"]
}
```

**Expected SSE Events (with HITL pause):**
```
event: status
data: {"event_type": "status", "data": {"status": "processing", "session_id": "sess-456"}}

event: phase_started
data: {"event_type": "phase_started", "data": {"phase": "intent", "message": "Analyzing request..."}}

event: intent_detected
data: {"event_type": "intent_detected", "data": {"request_type": "create", "document_type": "investment_memo"}}

event: phase_started
data: {"event_type": "phase_started", "data": {"phase": "planning", "message": "Creating execution plan..."}}

event: plan_generated
data: {"event_type": "plan_generated", "data": {"plan_id": "plan-789", "sections": [...]}}

event: awaiting_confirmation
data: {"event_type": "awaiting_confirmation", "data": {"session_id": "sess-456", "plan": {...}, "message": "Please review and approve the execution plan."}}

event: status
data: {"event_type": "status", "data": {"status": "paused", "session_id": "sess-456", "interrupt_type": "confirmation", "resume_endpoint": "/v1/copilot/stream/resume"}}
```

---

### 2.3 Stream - Agent Edit Mode

```bash
curl -X POST http://localhost:8000/v1/copilot/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "tenant_id": "tenant-123",
    "user_id": "user-456",
    "message": "Add a competitor analysis section comparing to DoorDash and Uber Eats",
    "type": "agent",
    "agent_case": "edit",
    "current_artifact": {
        "artifact_id": "art-memo-001",
        "artifact_type": "investment_memo",
        "title": "Wonder Group Inc - Investment Memo",
        "content": "# Investment Memo\n\n## Executive Summary\nWonder Group Inc is building the first fully vertically integrated food delivery platform...",
        "metadata": {}
    },
    "enabled_mcps": ["deals"],
    "web_search_enabled": true
  }'
```

**Postman Body (JSON):**
```json
{
    "tenant_id": "tenant-123",
    "user_id": "user-456",
    "message": "Add a competitor analysis section comparing to DoorDash and Uber Eats",
    "type": "agent",
    "agent_case": "edit",
    "current_artifact": {
        "artifact_id": "art-memo-001",
        "artifact_type": "investment_memo",
        "title": "Wonder Group Inc - Investment Memo",
        "content": "# Investment Memo\n\n## Executive Summary\nWonder Group Inc is building the first fully vertically integrated food delivery platform...",
        "metadata": {}
    },
    "enabled_mcps": ["deals"],
    "web_search_enabled": true
}
```

---

## 3. Resume Endpoint (`/v1/copilot/stream/resume`)

Use this endpoint after receiving a `status: paused` event from `/stream`.

### 3.1 Resume - Clarification Response

When the system asks clarification questions.

```bash
curl -X POST http://localhost:8000/v1/copilot/stream/resume \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "session_id": "sess-456",
    "clarification_response": {
        "q1": "Wonder Group Inc",
        "q2": "Focus on vertical integration model and FLASH technology",
        "q3": "3-5 pages"
    }
  }'
```

**Postman Body (JSON):**
```json
{
    "session_id": "sess-456",
    "clarification_response": {
        "q1": "Wonder Group Inc",
        "q2": "Focus on vertical integration model and FLASH technology",
        "q3": "3-5 pages"
    }
}
```

**Expected SSE Events:**
```
event: clarification_resolved
data: {"event_type": "clarification_resolved", "data": {"session_id": "sess-456", "responses": {...}}}

event: status
data: {"event_type": "status", "data": {"status": "resuming", "session_id": "sess-456"}}

event: phase_started
data: {"event_type": "phase_started", "data": {"phase": "planning"}}

... (continues with normal flow)
```

---

### 3.2 Resume - Plan Approved

Approve the execution plan to continue.

```bash
curl -X POST http://localhost:8000/v1/copilot/stream/resume \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "session_id": "sess-456",
    "confirmation_response": "approved"
  }'
```

**Postman Body (JSON):**
```json
{
    "session_id": "sess-456",
    "confirmation_response": "approved"
}
```

**Expected SSE Events:**
```
event: confirmation_received
data: {"event_type": "confirmation_received", "data": {"session_id": "sess-456", "response": "approved"}}

event: status
data: {"event_type": "status", "data": {"status": "resuming", "session_id": "sess-456"}}

event: fetching_mcp_data
data: {"event_type": "fetching_mcp_data", "data": {"domain": "deals"}}

event: mcp_data_received
data: {"event_type": "mcp_data_received", "data": {"domain": "deals", "data_keys": ["opportunity", "prescreening"]}}

event: synthesis_started
data: {"event_type": "synthesis_started", "data": {"message": "Synthesizing data..."}}

event: template_selected
data: {"event_type": "template_selected", "data": {"template_id": "investment_memo_v1", "section_count": 5}}

event: section_started
data: {"event_type": "section_started", "data": {"section_id": "exec_summary", "section_name": "Executive Summary"}}

event: section_completed
data: {"event_type": "section_completed", "data": {"section_id": "exec_summary", "word_count": 250}}

event: review_completed
data: {"event_type": "review_completed", "data": {"coherence_score": 0.92, "issues_count": 1, "approved": true}}

event: artifact_update
data: {"event_type": "artifact_update", "data": {"artifact_id": "art-new-001", "title": "Wonder Group Inc - Investment Memo", "content": "..."}}

event: final
data: {"event_type": "final", "data": {"session_id": "sess-456", "type": "agent", "artifact_count": 1}}
```

---

### 3.3 Resume - Plan Modify

Request modifications to the plan before proceeding.

```bash
curl -X POST http://localhost:8000/v1/copilot/stream/resume \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "session_id": "sess-456",
    "confirmation_response": "modify",
    "plan_modifications": [
        "Add an ESG section after Investment Thesis",
        "Remove the Appendix section",
        "Focus more on competitive landscape"
    ]
  }'
```

**Postman Body (JSON):**
```json
{
    "session_id": "sess-456",
    "confirmation_response": "modify",
    "plan_modifications": [
        "Add an ESG section after Investment Thesis",
        "Remove the Appendix section",
        "Focus more on competitive landscape"
    ]
}
```

**Expected SSE Events:**
```
event: confirmation_received
data: {"event_type": "confirmation_received", "data": {"session_id": "sess-456", "response": "modify"}}

event: status
data: {"event_type": "status", "data": {"status": "resuming", "session_id": "sess-456"}}

event: phase_started
data: {"event_type": "phase_started", "data": {"phase": "planning", "message": "Revising plan..."}}

event: plan_generated
data: {"event_type": "plan_generated", "data": {"plan_id": "plan-790", "sections": [...]}}

event: awaiting_confirmation
data: {"event_type": "awaiting_confirmation", "data": {"session_id": "sess-456", "plan": {...}}}

event: status
data: {"event_type": "status", "data": {"status": "paused", "interrupt_type": "confirmation"}}
```

---

### 3.4 Resume - Plan Cancelled

Cancel the execution entirely.

```bash
curl -X POST http://localhost:8000/v1/copilot/stream/resume \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "session_id": "sess-456",
    "confirmation_response": "cancelled"
  }'
```

**Postman Body (JSON):**
```json
{
    "session_id": "sess-456",
    "confirmation_response": "cancelled"
}
```

**Expected SSE Events:**
```
event: confirmation_received
data: {"event_type": "confirmation_received", "data": {"session_id": "sess-456", "response": "cancelled"}}

event: status
data: {"event_type": "status", "data": {"status": "resuming", "session_id": "sess-456"}}

event: final
data: {"event_type": "final", "data": {"session_id": "sess-456", "type": "agent", "artifact_count": 0, "current_phase": "complete"}}
```

---

## 4. Error Scenarios

### 4.1 Missing Required Fields

```bash
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hello"
  }'
```

**Expected Response (422 Validation Error):**
```json
{
    "detail": [
        {
            "loc": ["body", "tenant_id"],
            "msg": "field required",
            "type": "value_error.missing"
        },
        {
            "loc": ["body", "user_id"],
            "msg": "field required",
            "type": "value_error.missing"
        }
    ]
}
```

---

### 4.2 Invalid Session ID for Resume

```bash
curl -X POST http://localhost:8000/v1/copilot/stream/resume \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "non-existent-session-id",
    "confirmation_response": "approved"
  }'
```

**Expected SSE Error Event:**
```
event: error
data: {"event_type": "error", "data": {"error": "No paused session found for session_id: non-existent-session-id"}}
```

---

### 4.3 Invalid Confirmation Response

```bash
curl -X POST http://localhost:8000/v1/copilot/stream/resume \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "sess-456",
    "confirmation_response": "invalid_value"
  }'
```

**Expected Response (422 Validation Error):**
```json
{
    "detail": [
        {
            "loc": ["body", "confirmation_response"],
            "msg": "value is not a valid enumeration member; permitted: 'approved', 'modify', 'cancelled'",
            "type": "type_error.enum"
        }
    ]
}
```

---

### 4.4 Agent Edit Without Artifact

```bash
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "tenant-123",
    "user_id": "user-456",
    "message": "Add a new section",
    "type": "agent",
    "agent_case": "edit"
  }'
```

**Expected Response (400 Bad Request):**
```json
{
    "error": "Bad Request",
    "detail": "current_artifact is required for agent edit mode"
}
```

---

### 4.5 State Persistence Unavailable (Resume)

When Cosmos DB is not configured/available.

```bash
curl -X POST http://localhost:8000/v1/copilot/stream/resume \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "sess-456",
    "confirmation_response": "approved"
  }'
```

**Expected Response (503 Service Unavailable):**
```json
{
    "error": "Service Unavailable",
    "detail": "State persistence not available. Cannot resume session."
}
```

---

## Postman Collection Tips

### Headers

Set these headers for all requests:

| Header | Value |
|--------|-------|
| `Content-Type` | `application/json` |
| `Accept` | `text/event-stream` (for streaming endpoints) |

### Environment Variables

Create these variables in Postman:

| Variable | Example Value |
|----------|---------------|
| `base_url` | `http://localhost:8000` |
| `tenant_id` | `tenant-123` |
| `user_id` | `user-456` |
| `session_id` | `{{last_session_id}}` |
| `opportunity_id` | `opp-001` |

### Pre-request Script (Extract session_id)

Add this to tests tab to capture session_id for follow-up requests:

```javascript
// For non-streaming responses
if (pm.response.json().session_id) {
    pm.environment.set("last_session_id", pm.response.json().session_id);
}
```

---

## Quick Reference

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/v1/copilot/chat` | POST | Non-streaming chat (ask/agent) |
| `/v1/copilot/stream` | POST | SSE streaming with HITL support |
| `/v1/copilot/stream/resume` | POST | Resume paused HITL execution |

| Request Type | `type` | `agent_case` | Use Case |
|--------------|--------|--------------|----------|
| Ask | `ask` | - | Q&A, queries |
| Agent Create | `agent` | `create` | Generate new artifacts |
| Agent Edit | `agent` | `edit` | Modify existing artifacts |

| Resume Response | `confirmation_response` | Effect |
|-----------------|-------------------------|--------|
| Approve | `approved` | Continue execution |
| Modify | `modify` | Return to planning with changes |
| Cancel | `cancelled` | End execution |
