# Ask Mode - Streaming Postman Requests

This document contains all Ask mode API request examples for the streaming endpoint (`/v1/copilot/stream`).

## Base URL

```
http://localhost:8000
```

---

## Table of Contents

- [1. Simple Question](#1-simple-question)
- [2. With Page Context](#2-with-page-context)
- [3. With Document Selection (RAG)](#3-with-document-selection-rag)
- [4. With Web Search](#4-with-web-search)
- [5. Multi-turn Conversation](#5-multi-turn-conversation)
- [6. Comprehensive Examples](#6-comprehensive-examples)
  - [6.1 Single-Turn: Web + RAG + MCP](#61-single-turn-web--rag--mcp)
  - [6.2 Multi-Turn: Web + RAG + MCP](#62-multi-turn-web--rag--mcp)

---

## 1. Simple Question

Minimal payload for a simple Q&A request with streaming response.

**cURL:**
```bash
curl -X POST http://localhost:8000/v1/copilot/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "tenant_id": "raoof-copilot-test-woner",
    "user_id": "user-456",
    "message": "What is the target raise for this opportunity?",
    "type": "ask"
  }'
```

**Postman Body (JSON):**
```json
{
    "tenant_id": "raoof-copilot-test-woner",
    "user_id": "user-456",
    "message": "What is the target raise for this opportunity?",
    "type": "ask"
}
```

## 2. With Page Context

Include current page context for opportunity-specific queries with streaming response.

**cURL:**
```bash
curl -X POST http://localhost:8000/v1/copilot/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "tenant_id": "raoof-copilot-test-woner",
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
  }'
```

**Postman Body (JSON):**
```json
{
    "tenant_id": "raoof-copilot-test-woner",
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

## 3. With Document Selection (RAG)

Query with selected documents for RAG-based extraction with streaming response.

**cURL:**
```bash
curl -X POST http://localhost:8000/v1/copilot/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
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

## 4. With Web Search

Enable web search for real-time information with streaming response.

**cURL:**
```bash
curl -X POST http://localhost:8000/v1/copilot/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "tenant_id": "raoof-copilot-test-woner",
    "user_id": "user-456",
    "message": "What are the latest ESG trends in private equity for 2024?",
    "type": "ask",
    "web_search_enabled": true
  }'
```

**Postman Body (JSON):**
```json
{
    "tenant_id": "raoof-copilot-test-woner",
    "user_id": "user-456",
    "message": "What are the latest ESG trends in private equity for 2024?",
    "type": "ask",
    "web_search_enabled": true
}
```

## 6. Comprehensive Examples

### 6.1 Single-Turn: Web + RAG + MCP

This example combines all three data sources in a single streaming request: MCP for structured data, RAG for document analysis, and Web Search for real-time market information.

**Use Case:** Analyze a deal using internal data (MCP), uploaded documents (RAG), and current market trends (Web) with real-time streaming updates.

**cURL:**
```bash
curl -X POST http://localhost:8000/v1/copilot/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "tenant_id": "raoof-copilot-test-woner",
    "user_id": "user-456",
    "message": "Provide a comprehensive analysis of Wonder Group Inc including deal details from our system, risks from the due diligence documents, and current food-tech market trends",
    "additional_prompt": "You have access to these tools/data sources:\n1) MCPs (structured internal system data)\n2) RAG (our uploaded/internal documents already indexed)\n3) Web Search (external, real-time information)\n\nTool priority rules:\n- Always try MCPs first for deal/system facts and structured fields.\n- If MCPs do not have the needed information, then use RAG to extract from the selected/uploaded documents.\n- Only if MCPs and RAG are insufficient, use Web Search for external context (e.g., market trends, competitors, news).\n\nNon-cascading rule:\n- If you already got sufficient information from MCPs, do NOT use RAG or Web Search.\n- If you already got sufficient information from RAG, do NOT use Web Search.\n- Use only the minimum set of tools needed to answer.\n\nOutput rule:\n- The final write-up must be based primarily on the highest-priority source that provided the answer.\n- Clearly distinguish what comes from internal system data vs uploaded documents vs external web, but do not fetch lower-priority sources if not required.",
    "type": "ask",
    "module_id": "deals",
    "page_context": {
        "module_id": "deals",
        "screen_name": "opportunity_detail",
        "opportunity_id": "opp-001",
        "opportunity_name": "Wonder Group Inc",
        "screen_highlights": {
            "sector": "Food Technology",
            "stage": "SAFE Note",
            "target_raise": "$350M"
        }
    },
    "selected_docs": {
        "doc_ids": [
            "c75e341a-2953-4672-b85b-6c9b4583b0da",
            "a6077903-0d41-4a16-8131-4442bf4d0046",
            "cd5774d3-407d-46ce-9818-0e069e705dd7",
            "ff6c110e-d323-47c8-a472-7bfa5f1a257a"
        ],
        "doc_sets": ["due_diligence", "financials"],
        "storage": {
            "account_url": "https://stinvictusuaenorthdev.blob.core.windows.net",
            "filesystem": "documents",
            "base_prefix": "tenants/raoof-copilot-test-woner/modules/invictus-deals/use-cases/test-01/pre-screening-report/documents/"
        }
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
    "message": "Provide a comprehensive analysis of Wonder Group Inc including deal details from our system, risks from the due diligence documents, and current food-tech market trends",
    "additional_prompt": "You have access to these tools/data sources:\n1) MCPs (structured internal system data)\n2) RAG (our uploaded/internal documents already indexed)\n3) Web Search (external, real-time information)\n\nTool priority rules:\n- Always try MCPs first for deal/system facts and structured fields.\n- If MCPs do not have the needed information, then use RAG to extract from the selected/uploaded documents.\n- Only if MCPs and RAG are insufficient, use Web Search for external context (e.g., market trends, competitors, news).\n\nNon-cascading rule:\n- If you already got sufficient information from MCPs, do NOT use RAG or Web Search.\n- If you already got sufficient information from RAG, do NOT use Web Search.\n- Use only the minimum set of tools needed to answer.\n\nOutput rule:\n- The final write-up must be based primarily on the highest-priority source that provided the answer.\n- Clearly distinguish what comes from internal system data vs uploaded documents vs external web, but do not fetch lower-priority sources if not required.",
    "type": "ask",
    "module_id": "deals",
    "page_context": {
        "module_id": "deals",
        "screen_name": "opportunity_detail",
        "opportunity_id": "opp-001",
        "opportunity_name": "Wonder Group Inc",
        "screen_highlights": {
            "sector": "Food Technology",
            "stage": "SAFE Note",
            "target_raise": "$350M"
        }
    },
    "selected_docs": {
        "doc_ids": [
            "c75e341a-2953-4672-b85b-6c9b4583b0da",
            "a6077903-0d41-4a16-8131-4442bf4d0046",
            "cd5774d3-407d-46ce-9818-0e069e705dd7",
            "ff6c110e-d323-47c8-a472-7bfa5f1a257a"
        ],
        "doc_sets": ["due_diligence", "financials"],
        "storage": {
            "account_url": "https://stinvictusuaenorthdev.blob.core.windows.net",
            "filesystem": "documents",
            "base_prefix": "tenants/raoof-copilot-test-woner/modules/invictus-deals/use-cases/test-01/pre-screening-report/documents/"
        }
    },
    "enabled_mcps": ["deals"],
    "web_search_enabled": true
}
```

### 6.2 Multi-Turn: Web + RAG + MCP

This example shows a multi-turn conversation leveraging all three data sources with streaming responses, demonstrating context retention across turns.

#### Turn 1: Initial Comprehensive Query

**Postman Body (JSON):**
```json
{
    "tenant_id": "raoof-copilot-test-woner",
    "user_id": "user-456",
    "message": "Compare Wonder Group Inc's financials with the projections from the documents, and tell me how they align with current food-tech valuations",
    "type": "ask",
    "module_id": "deals",
    "page_context": {
        "module_id": "deals",
        "screen_name": "opportunity_detail",
        "opportunity_id": "opp-001",
        "opportunity_name": "Wonder Group Inc"
    },
    "selected_docs": {
        "doc_ids": [
            "ff6c110e-d323-47c8-a472-7bfa5f1a257a"
        ],
        "storage": {
            "account_url": "https://stinvictusuaenorthdev.blob.core.windows.net",
            "filesystem": "documents",
            "base_prefix": "tenants/raoof-copilot-test-woner/modules/invictus-deals/use-cases/test-01/pre-screening-report/documents/"
        }
    },
    "enabled_mcps": ["deals"],
    "web_search_enabled": true
}
```

#### Turn 2: Follow-up Drilling into Risks

**Postman Body (JSON):**
```json
{
    "tenant_id": "raoof-copilot-test-woner",
    "user_id": "user-456",
    "message": "Given those projections, what are the biggest execution risks and how do they compare to risks faced by competitors?",
    "type": "ask",
    "session_id": "sess-multiturn-comprehensive-001",
    "selected_docs": {
        "doc_ids": [
            "c75e341a-2953-4672-b85b-6c9b4583b0da",
            "cd5774d3-407d-46ce-9818-0e069e705dd7"
        ],
        "doc_sets": ["due_diligence", "risk_assessment"],
        "storage": {
            "account_url": "https://stinvictusuaenorthdev.blob.core.windows.net",
            "filesystem": "documents",
            "base_prefix": "tenants/raoof-copilot-test-woner/modules/invictus-deals/use-cases/test-01/pre-screening-report/documents/"
        }
    },
    "enabled_mcps": ["deals"],
    "web_search_enabled": true
}
```

#### Turn 3: Investment Recommendation

**Postman Body (JSON):**
```json
{
    "tenant_id": "raoof-copilot-test-woner",
    "user_id": "user-456",
    "message": "Based on everything we've discussed, what's your recommendation on whether we should proceed with this deal?",
    "type": "ask",
    "session_id": "sess-multiturn-comprehensive-001",
    "enabled_mcps": ["deals"]
}
```


---

## Postman Collection Tips

### Headers

Set these headers for all streaming requests:

| Header | Value |
|--------|-------|
| `Content-Type` | `application/json` |
| `Accept` | `text/event-stream` |

**Important:** The `Accept: text/event-stream` header is required for streaming endpoints. Postman will display the SSE events in real-time.

### Environment Variables

Create these variables in Postman for easier testing:

| Variable | Example Value | Description |
|----------|---------------|-------------|
| `base_url` | `http://localhost:8000` | API base URL |
| `tenant_id` | `raoof-copilot-test-woner` | Your tenant ID |
| `user_id` | `user-456` | Test user ID |
| `session_id` | `{{last_session_id}}` | Auto-populated from response |
| `opportunity_id` | `opp-001` | Test opportunity ID |
| `doc_id_1` | `c75e341a-2953-4672-b85b-6c9b4583b0da` | Document ID 1 |
| `doc_id_2` | `a6077903-0d41-4a16-8131-4442bf4d0046` | Document ID 2 |
| `storage_url` | `https://stinvictusuaenorthdev.blob.core.windows.net` | Azure storage URL |
| `storage_prefix` | `tenants/raoof-copilot-test-woner/modules/invictus-deals/use-cases/test-01/pre-screening-report/documents/` | Storage path prefix |

### Test Script (Extract session_id from SSE)

Add this to the **Tests** tab to automatically capture `session_id` from SSE events:

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

