# Invictus Copilot API - Postman Requests

This document contains all API request examples for testing the Copilot API endpoints using Postman or cURL.

## Base URL

```
http://localhost:8000
```

---

## Table of Contents
- [1. Set 1: Agent Create Mode Workflows](#1-set-1-agent-create-mode-workflows)
  - [1.1 Agent Create Mode (Without Template)](#11-agent-create-mode-without-template)
  - [1.2 Agent Create Mode (With Template)](#12-agent-create-mode-with-template)
  - [1.3 Resume - Clarification Response](#13-resume---clarification-response)
  - [1.4 Resume - Plan Approved (Confirm)](#14-resume---plan-approved-confirm)
  - [1.5 Resume - Plan Modify](#15-resume---plan-modify)
  - [1.6 Resume - Plan Cancelled](#16-resume---plan-cancelled)
- [2. Set 2: Editing Existing Artifact](#2-set-2-editing-existing-artifact)
  - [2.1 Edit Mode](#21-edit-mode)
- [3. Set 3: Fill Mode](#3-set-3-fill-mode)
- [4. Response Structures](#4-response-structures)
  - [4.1 HITL Events (Awaiting Confirmation)](#41-hitl-events-awaiting-confirmation)
  - [4.2 Final Event](#42-final-event)
- [5. Error Scenarios](#5-error-scenarios)

---

## 1. Set 1: Agent Create Mode Workflows

The unified streaming endpoint (`/v1/copilot/stream`) handles both new requests and resuming paused sessions. When a `session_id` is provided and the session is paused, it automatically resumes with the provided response.

### 1.1 Agent Create Mode (Without Template)

Basic create request. This will trigger HITL gates (clarification and confirmation).

**cURL:**
```bash
curl -X POST http://localhost:8000/v1/copilot/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "tenant_id": "raoof-copilot-test-woner",
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
    "enabled_mcps": ["deals"],
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
    "message": "Create an investment memo for this opportunity",
    "type": "agent",
    "agent_case": "create",
    "page_context": {
        "module_id": "deals",
        "screen_name": "opportunity_detail",
        "opportunity_id": "opp-001",
        "opportunity_name": "Wonder Group Inc"
    },
    "enabled_mcps": ["deals"],
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

### 1.2 Agent Create Mode (With Template)

Create request with a template structure. The agent will follow the template fields.

**cURL:**
```bash
curl -X POST http://localhost:8000/v1/copilot/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "tenant_id": "raoof-copilot-test-woner",
    "user_id": "user-456",
    "message": "Create an investment memo for Wonder Group",
    "type": "agent",
    "agent_case": "create",
    "page_context": {
        "module_id": "deals",
        "screen_name": "opportunity_detail",
        "opportunity_id": "opp-001",
        "opportunity_name": "Wonder Group Inc"
    },
    "additional_prompt": "Focus on the vertical integration model and FLASH technology. This is for the investment committee meeting.",
    "template": {
        "fields": {
            "executive_summary": {
                "description": "High-level summary of the investment opportunity",
                "instruction": "Write a 2-3 paragraph summary covering company overview, investment thesis, and key metrics",
                "type": "string",
                "required": true
            },
            "financial_analysis": {
                "description": "Financial metrics and projections",
                "instruction": "Include revenue, margins, growth rates, and valuation multiples. Extract from MCP data and documents.",
                "type": "string",
                "required": true
            },
            "investment_highlights": {
                "description": "Key reasons to invest",
                "instruction": "List 3-5 key investment highlights as bullet points",
                "type": "string",
                "required": true
            },
            "risk_factors": {
                "description": "Key risks to consider",
                "instruction": "Identify and describe 3-5 key risks",
                "type": "string",
                "required": false
            }
        }
    },
    "enabled_mcps": ["deals"],
    "web_search_enabled": true,
    "selected_docs": {
        "doc_ids": ["c75e341a-2953-4672-b85b-6c9b4583b0da", "a6077903-0d41-4a16-8131-4442bf4d0046", "cd5774d3-407d-46ce-9818-0e069e705dd7", "ff6c110e-d323-47c8-a472-7bfa5f1a257a"],
        "doc_sets": ["due_diligence", "financials"],
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
    "message": "Create an investment memo for Wonder Group",
    "type": "agent",
    "agent_case": "create",
    "page_context": {
        "module_id": "deals",
        "screen_name": "opportunity_detail",
        "opportunity_id": "opp-001",
        "opportunity_name": "Wonder Group Inc"
    },
    "additional_prompt": "Focus on the vertical integration model and FLASH technology. This is for the investment committee meeting.",
    "template": {
        "fields": {
            "executive_summary": {
                "description": "High-level summary of the investment opportunity",
                "instruction": "Write a 2-3 paragraph summary covering company overview, investment thesis, and key metrics",
                "type": "string",
                "required": true
            },
            "financial_analysis": {
                "description": "Financial metrics and projections",
                "instruction": "Include revenue, margins, growth rates, and valuation multiples. Extract from MCP data and documents.",
                "type": "string",
                "required": true
            },
            "investment_highlights": {
                "description": "Key reasons to invest",
                "instruction": "List 3-5 key investment highlights as bullet points",
                "type": "string",
                "required": true
            },
            "risk_factors": {
                "description": "Key risks to consider",
                "instruction": "Identify and describe 3-5 key risks",
                "type": "string",
                "required": false
            }
        }
    },
    "enabled_mcps": ["deals"],
    "web_search_enabled": true,
    "selected_docs": {
        "doc_ids": ["c75e341a-2953-4672-b85b-6c9b4583b0da", "a6077903-0d41-4a16-8131-4442bf4d0046", "cd5774d3-407d-46ce-9818-0e069e705dd7", "ff6c110e-d323-47c8-a472-7bfa5f1a257a"],
        "doc_sets": ["due_diligence", "financials"],
        "storage": {
            "account_url": "https://stinvictusuaenorthdev.blob.core.windows.net",
            "filesystem": "documents",
            "base_prefix": "tenants/raoof-copilot-test-woner/modules/invictus-deals/use-cases/test-01/pre-screening-report/documents/"
        }
    }
}
```

---

### 1.3 Resume - Clarification Response

When the system asks clarification questions (e.g., missing financial data, risk factors, market analysis), respond with your answers in the `message` field and set `confirmation_response` to `"clarified"`.

**Example clarification_required event:**
```json
{
  "missing_inputs": [
    "specific financial data for Wonder Group",
    "key risks and mitigations",
    "market analysis details",
    "expected returns or valuation metrics"
  ]
}
```

**cURL:**
```bash
curl -X POST http://localhost:8000/v1/copilot/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "tenant_id": "raoof-copilot-test-woner",
    "user_id": "user-456",
    "session_id": "YOUR_SESSION_ID_FROM_CLARIFICATION_EVENT",
    "message": "Financial data: Revenue is $407M TTM with 35% YoY growth, gross margin 45%, targeting profitability by 2026. Key risks: High competition from DoorDash and Uber Eats, dependency on restaurant partnerships, regulatory risks in food service. Market analysis: TAM is $150B globally, Wonder targets premium segment with 15% market share goal. Expected returns: 3-5x in 5 years, entry valuation at $2.5B.",
    "type": "agent",
    "confirmation_response": "clarified"
  }'
```

**Postman Body (JSON):**
```json
{
    "tenant_id": "raoof-copilot-test-woner",
    "user_id": "user-456",
    "session_id": "YOUR_SESSION_ID_FROM_CLARIFICATION_EVENT",
    "message": "Financial data: Revenue is $407M TTM with 35% YoY growth, gross margin 45%, targeting profitability by 2026. Key risks: High competition from DoorDash and Uber Eats, dependency on restaurant partnerships, regulatory risks in food service. Market analysis: TAM is $150B globally, Wonder targets premium segment with 15% market share goal. Expected returns: 3-5x in 5 years, entry valuation at $2.5B.",
    "type": "agent",
    "confirmation_response": "clarified"
}
```

---

### 1.4 Resume - Plan Approved (Confirm)

Approve the execution plan to continue. This confirms the plan and proceeds with execution.

**cURL:**
```bash
curl -X POST http://localhost:8000/v1/copilot/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "tenant_id": "raoof-copilot-test-woner",
    "user_id": "user-456",
    "session_id": "sess-456",
    "message": "",
    "type": "agent",
    "confirmation_response": "approved"
  }'
```

**Postman Body (JSON):**
```json
{
    "tenant_id": "raoof-copilot-test-woner",
    "user_id": "user-456",
    "session_id": "sess-456",
    "message": "",
    "type": "agent",
    "confirmation_response": "approved"
}
```

---

### 1.5 Resume - Plan Modify

Request modifications to the plan before proceeding. Put your modification requests in the `message` field as natural language.

**cURL:**
```bash
curl -X POST http://localhost:8000/v1/copilot/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "tenant_id": "raoof-copilot-test-woner",
    "user_id": "user-456",
    "session_id": "sess-456",
    "message": "Add an ESG section after Investment Thesis. Remove the Appendix section. Focus more on competitive landscape.",
    "type": "agent",
    "confirmation_response": "modify"
  }'
```

**Postman Body (JSON):**
```json
{
    "tenant_id": "raoof-copilot-test-woner",
    "user_id": "user-456",
    "session_id": "sess-456",
    "message": "Add an ESG section after Investment Thesis. Remove the Appendix section. Focus more on competitive landscape.",
    "type": "agent",
    "confirmation_response": "modify"
}
```

---

### 1.6 Resume - Plan Cancelled

Cancel the execution entirely. This ends the session without creating the artifact.

**cURL:**
```bash
curl -X POST http://localhost:8000/v1/copilot/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "tenant_id": "raoof-copilot-test-woner",
    "user_id": "user-456",
    "session_id": "sess-456",
    "message": "",
    "type": "agent",
    "confirmation_response": "cancelled"
  }'
```

**Postman Body (JSON):**
```json
{
    "tenant_id": "raoof-copilot-test-woner",
    "user_id": "user-456",
    "session_id": "sess-456",
    "message": "",
    "type": "agent",
    "confirmation_response": "cancelled"
}
```

---

## 2. Set 2: Editing Existing Artifact

Edit mode allows you to modify content that has already been created. Provide the `artifact_id` and optionally a `session_id` to maintain conversation context from the create flow.

### 2.1 Edit Mode

Edit an existing artifact by providing the `artifact_id`. The system automatically fetches the content from storage.

**Parameters:**
- `artifact_id` (required): The ID of the artifact to edit
- `session_id` (optional): Include the session ID from the create flow to maintain conversation context

**Note:** The artifact must exist in CosmosDB storage (created via a previous agent create flow).

**cURL:**
```bash
curl -X POST http://localhost:8000/v1/copilot/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "tenant_id": "raoof-copilot-test-woner",
    "user_id": "user-456",
    "session_id": "YOUR_SESSION_ID_FROM_CREATE_FLOW",
    "message": "Add a competitor analysis section comparing to DoorDash and Uber Eats",
    "type": "agent",
    "agent_case": "edit",
    "current_artifact": {
        "artifact_id": "e0d1885e"
    },
    "enabled_mcps": ["deals"],
    "web_search_enabled": true
  }'
```

**Postman Body (JSON):**
```json
{
    "tenant_id": "raoof-copilot-test-woner",
    "user_id": "user-456",
    "session_id": "YOUR_SESSION_ID_FROM_CREATE_FLOW",
    "message": "Add a competitor analysis section comparing to DoorDash and Uber Eats",
    "type": "agent",
    "agent_case": "edit",
    "current_artifact": {
        "artifact_id": "e0d1885e"
    },
    "enabled_mcps": ["deals"],
    "web_search_enabled": true
}
```

**How it works:**
1. The system receives the request with `artifact_id` (and optionally `session_id`)
2. It queries CosmosDB artifacts container for the artifact content
3. If `session_id` is provided, conversation context from the create flow is maintained
4. If artifact not found, the system will request clarification (asking for the artifact content)

---

## 3. Set 3: Fill Mode

Fill mode is used for structured form filling (prescreening questionnaires, intake forms, etc.). The agent fills template fields based on available data sources.

**cURL:**
```bash
curl -X POST http://localhost:8000/v1/copilot/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "tenant_id": "raoof-copilot-test-woner",
    "user_id": "user-456",
    "message": "Fill out the prescreening questionnaire for this opportunity",
    "type": "agent",
    "agent_case": "fill",
    "page_context": {
        "module_id": "deals",
        "opportunity_id": "opp-001",
        "opportunity_name": "Wonder Group Inc"
    },
    "template": {
        "fields": {
            "company_name": {
                "description": "Full legal name of the company",
                "instruction": "Extract from company documents or page context",
                "type": "string",
                "required": true
            },
            "investment_stage": {
                "description": "Current investment stage",
                "instruction": "Determine based on company metrics and history",
                "type": "string",
                "options": ["Seed", "Series A", "Series B", "Series C+", "Growth"],
                "required": true
            },
            "revenue_ttm": {
                "description": "Trailing twelve months revenue in USD",
                "instruction": "Extract from financial documents or MCP data",
                "type": "number",
                "required": false
            },
            "employee_count": {
                "description": "Current number of employees",
                "instruction": "Extract from company information or documents",
                "type": "number",
                "required": false
            },
            "headquarters_location": {
                "description": "Company headquarters city and country",
                "instruction": "Extract from company information",
                "type": "string",
                "required": true
            },
            "key_risks": {
                "description": "Primary risk factors identified",
                "instruction": "Identify top 3 risks from available information",
                "type": "array",
                "required": false
            }
        }
    },
    "enabled_mcps": ["deals"],
    "selected_docs": {
        "doc_ids": ["c75e341a-2953-4672-b85b-6c9b4583b0da", "a6077903-0d41-4a16-8131-4442bf4d0046", "cd5774d3-407d-46ce-9818-0e069e705dd7", "ff6c110e-d323-47c8-a472-7bfa5f1a257a"],
        "doc_sets": ["due_diligence", "financials"],
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
    "message": "Fill out the prescreening questionnaire for this opportunity",
    "type": "agent",
    "agent_case": "fill",
    "page_context": {
        "module_id": "deals",
        "opportunity_id": "opp-001",
        "opportunity_name": "Wonder Group Inc"
    },
    "template": {
        "fields": {
            "company_name": {
                "description": "Full legal name of the company",
                "instruction": "Extract from company documents or page context",
                "type": "string",
                "required": true
            },
            "investment_stage": {
                "description": "Current investment stage",
                "instruction": "Determine based on company metrics and history",
                "type": "string",
                "options": ["Seed", "Series A", "Series B", "Series C+", "Growth"],
                "required": true
            },
            "revenue_ttm": {
                "description": "Trailing twelve months revenue in USD",
                "instruction": "Extract from financial documents or MCP data",
                "type": "number",
                "required": false
            },
            "employee_count": {
                "description": "Current number of employees",
                "instruction": "Extract from company information or documents",
                "type": "number",
                "required": false
            },
            "headquarters_location": {
                "description": "Company headquarters city and country",
                "instruction": "Extract from company information",
                "type": "string",
                "required": true
            },
            "key_risks": {
                "description": "Primary risk factors identified",
                "instruction": "Identify top 3 risks from available information",
                "type": "array",
                "required": false
            }
        }
    },
    "enabled_mcps": ["deals"],
    "selected_docs": {
        "doc_ids": ["c75e341a-2953-4672-b85b-6c9b4583b0da", "a6077903-0d41-4a16-8131-4442bf4d0046", "cd5774d3-407d-46ce-9818-0e069e705dd7", "ff6c110e-d323-47c8-a472-7bfa5f1a257a"],
        "doc_sets": ["due_diligence", "financials"],
        "storage": {
            "account_url": "https://stinvictusuaenorthdev.blob.core.windows.net",
            "filesystem": "documents",
            "base_prefix": "tenants/raoof-copilot-test-woner/modules/invictus-deals/use-cases/test-01/pre-screening-report/documents/"
        }
    }
}
```

**Expected Fill Mode Response (output_for_system.filled_template):**
```json
{
    "company_name": "Wonder Group Inc",
    "investment_stage": "Series B",
    "revenue_ttm": 45000000,
    "employee_count": 250,
    "headquarters_location": "New York, USA",
    "key_risks": [
        "High competition in food delivery market",
        "Dependency on restaurant partnerships",
        "Regulatory risks in food service industry"
    ]
}
```

---

## 4. Response Structures

All agent responses include dual output format: `message_for_user` (human-readable) and `output_for_system` (structured JSON for backend).

### 4.1 HITL Events (Awaiting Confirmation)

When the agent needs user approval:

```
event: awaiting_confirmation
data: {
    "event_type": "awaiting_confirmation",
    "data": {
        "session_id": "sess-456",
        "message_for_user": {
            "type": "plan",
            "content": "I will create an Investment Memo with 4 sections: Executive Summary, Financial Analysis, Investment Highlights, and Risk Factors.",
            "plan_summary": {
                "sections": ["Executive Summary", "Financial Analysis", "Investment Highlights", "Risk Factors"],
                "complexity": "moderate",
                "template_strategy": "use_existing",
                "from_template": true
            }
        },
        "plan": {
            "plan_id": "plan-789",
            "sections": [...],
            "data_sources": ["mcp:deals", "rag:documents"],
            "tools_to_call": ["deals:get_opportunity_details"]
        },
        "options": ["approved", "modify", "cancelled"]
    }
}

event: status
data: {
    "event_type": "status",
    "data": {
        "status": "paused",
        "session_id": "sess-456",
        "interrupt_type": "confirmation"
    }
}
```

### 4.2 Final Event

Upon completion, the final event includes both message and structured output:

**For Create/Edit Mode:**
```
event: final
data: {
    "event_type": "final",
    "data": {
        "session_id": "sess-456",
        "message_for_user": {
            "type": "summary",
            "content": "I've created the Investment Memo for Wonder Group Inc with 4 sections: Executive Summary, Financial Analysis, Investment Highlights, and Risk Factors."
        },
        "output_for_system": {
            "operation": "create",
            "artifact": {
                "artifact_id": "art-001",
                "artifact_type": "investment_memo",
                "title": "Wonder Group Inc - Investment Memo",
                "content": "# Wonder Group Inc - Investment Memo\n\n## Executive Summary\n..."
            },
            "filled_template": null,
            "metadata": {
                "sections_count": 4,
                "word_count": 1250
            }
        },
        "citations": [...]
    }
}
```

**For Fill Mode:**
```
event: final
data: {
    "event_type": "final",
    "data": {
        "session_id": "sess-456",
        "message_for_user": {
            "type": "summary",
            "content": "I've filled 6 fields in the prescreening questionnaire. 5 of 6 required fields are complete."
        },
        "output_for_system": {
            "operation": "fill",
            "artifact": null,
            "filled_template": {
                "company_name": "Wonder Group Inc",
                "investment_stage": "Series B",
                "revenue_ttm": 45000000,
                "employee_count": 250,
                "headquarters_location": "New York, USA",
                "key_risks": [
                    "High competition in food delivery market",
                    "Dependency on restaurant partnerships",
                    "Regulatory risks in food service industry"
                ]
            },
            "metadata": {
                "fields_filled": 6,
                "total_fields": 6,
                "fill_rate": 1.0,
                "missing_required": []
            }
        },
        "citations": [...]
    }
}
```

---

## 5. Error Scenarios

### 5.1 Missing Required Fields

```bash
curl -X POST http://localhost:8000/v1/copilot/stream \
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

### 5.2 Invalid Session ID for Resume

When session doesn't exist or is not paused:

```bash
curl -X POST http://localhost:8000/v1/copilot/stream \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "raoof-copilot-test-woner",
    "user_id": "user-456",
    "session_id": "non-existent-session",
    "message": "",
    "type": "agent",
    "confirmation_response": "approved"
  }'
```

The system will treat this as a new request since no paused session is found.

---

### 5.3 Agent Edit Without Artifact

```bash
curl -X POST http://localhost:8000/v1/copilot/stream \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "raoof-copilot-test-woner",
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

### 5.4 Fill Mode Without Template

```bash
curl -X POST http://localhost:8000/v1/copilot/stream \
  -H "Content-Type: application/json" \
  -d '{
    "tenant_id": "raoof-copilot-test-woner",
    "user_id": "user-456",
    "message": "Fill out the form",
    "type": "agent",
    "agent_case": "fill"
  }'
```

**Expected Response (400 Bad Request):**
```json
{
    "error": "Bad Request",
    "detail": "template is required for agent fill mode"
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

| Variable | Example Value | Description |
|----------|---------------|-------------|
| `base_url` | `http://localhost:8000` | API base URL |
| `tenant_id` | `raoof-copilot-test-woner` | Your tenant ID |
| `user_id` | `user-456` | Test user ID |
| `session_id` | `{{last_session_id}}` | Auto-populated from response |
| `opportunity_id` | `opp-001` | Test opportunity ID |
| `doc_id_1` | `c75e341a-2953-4672-b85b-6c9b4583b0da` | Document ID 1 |
| `doc_id_2` | `a6077903-0d41-4a16-8131-4442bf4d0046` | Document ID 2 |
| `doc_id_3` | `cd5774d3-407d-46ce-9818-0e069e705dd7` | Document ID 3 |
| `doc_id_4` | `ff6c110e-d323-47c8-a472-7bfa5f1a257a` | Document ID 4 |
| `storage_url` | `https://stinvictusuaenorthdev.blob.core.windows.net` | Azure storage URL |
| `storage_prefix` | `tenants/raoof-copilot-test-woner/modules/invictus-deals/use-cases/test-01/pre-screening-report/documents/` | Storage path prefix |

### Pre-request Script (Extract session_id)

Add this to tests tab to capture session_id for follow-up requests:

```javascript
// Parse SSE events and extract session_id
var responseText = pm.response.text();
var lines = responseText.split('\n');

for (var i = 0; i < lines.length; i++) {
    if (lines[i].startsWith('data: ')) {
        try {
            var data = JSON.parse(lines[i].substring(6));
            if (data.event_type === 'status' && data.data && data.data.session_id) {
                pm.environment.set("last_session_id", data.data.session_id);
                console.log("Session ID saved: " + data.data.session_id);
                break;
            }
            if (data.event_type === 'final' && data.data && data.data.session_id) {
                pm.environment.set("last_session_id", data.data.session_id);
                console.log("Session ID saved: " + data.data.session_id);
            }
        } catch (e) {
            // Skip invalid JSON
        }
    }
}
```

---

## Quick Reference

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/v1/copilot/chat` | POST | Non-streaming chat (ask/agent) |
| `/v1/copilot/stream` | POST | SSE streaming with HITL support (unified endpoint) |

| Request Type | `type` | `agent_case` | Use Case |
|--------------|--------|--------------|----------|
| Ask | `ask` | - | Q&A, queries |
| Agent Create | `agent` | `create` | Generate new artifacts |
| Agent Edit | `agent` | `edit` | Modify existing artifacts |
| Agent Fill | `agent` | `fill` | Fill template fields |

| Resume Response | `confirmation_response` | `message` Contains | Effect |
|-----------------|-------------------------|-------------------|--------|
| Clarified | `clarified` | Answers to clarification questions | Continue to planning |
| Approve | `approved` | (optional) Additional instructions | Continue execution |
| Modify | `modify` | Modification requests as natural text | Return to planning with changes |
| Cancel | `cancelled` | (optional) Reason for cancellation | End execution |

### Template Field Properties

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `description` | string | Yes | What this field represents |
| `instruction` | string | Yes | How to fill this field |
| `type` | string | No | Field type: `string`, `number`, `boolean`, `object`, `array` |
| `options` | array | No | Allowed values for the field |
| `required` | boolean | No | Whether the field is required (default: true) |
