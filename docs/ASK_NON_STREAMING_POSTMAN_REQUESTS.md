# Ask Mode - Non-Streaming Postman Requests

This document contains all Ask mode API request examples for the non-streaming endpoint (`/v1/copilot/chat`).

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

Minimal payload for a simple Q&A request.

**cURL:**
```bash
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
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

**Expected Response:**
```json
{
    "session_id": "37017c42-45c6-4ee7-9ec1-a2f11befc829",
    "message": "I don't have enough information to determine the target raise for this opportunity.",
    "tool_results": [],
    "citations": [],
    "intent": "ask",
    "artifact": null,
    "edit_instructions": null,
    "hitl_status": null
}
```

---

## 2. With Page Context

Include current page context for opportunity-specific queries.

**cURL:**
```bash
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
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

**Expected Response:**
```json
{
    "session_id": "079333ac-a108-48b5-98f4-04b5c3fd2d75",
    "message": "The risk rating for this deal is **Medium**.",
    "tool_results": [
        {
            "tool_name": "deals:get_opportunity_details",
            "input_summary": "Get opportunity opp-001",
            "output_summary": "Retrieved: Wonder Group Inc",
            "latency_ms": 24.150000000000002,
            "success": true,
            "citations": []
        }
    ],
    "citations": [],
    "intent": "ask",
    "artifact": null,
    "edit_instructions": null,
    "hitl_status": null
}
```

---

## 3. With Document Selection (RAG)

Query with selected documents for RAG-based extraction.

**cURL:**
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

## 4. With Web Search

Enable web search for real-time information.

**cURL:**
```bash
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
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

---

## 6. Comprehensive Examples

### 6.1 Single-Turn: Web + RAG + MCP

This example combines all three data sources in a single request: MCP for structured data, RAG for document analysis, and Web Search for real-time market information.

**Use Case:** Analyze a deal using internal data (MCP), uploaded documents (RAG), and current market trends (Web).

**cURL:**
```bash
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
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

This example shows a multi-turn conversation leveraging all three data sources, demonstrating context retention across turns.

#### Turn 1: Initial Comprehensive Query

**Postman Body (JSON):**
```json
{
    "tenant_id": "raoof-copilot-test-woner",
    "user_id": "user-456",
    "message": "Compare Wonder Group Inc's financials with the projections in the uploaded documents, and tell me how they align with current food-tech valuations",
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
    "session_id": "sess-multiturn-002",
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
    "session_id": "sess-multiturn-002",
    "enabled_mcps": ["deals"]
}
```

**Expected Response (Turn 3):**
```json
{
    "session_id": "sess-multiturn-002",
    "type": "ask",
    "response": "## Investment Recommendation: Wonder Group Inc\n\n**Recommendation: PROCEED WITH CAUTION - Subject to further diligence on specific items**\n\n### Summary of Analysis\n\nBased on our comprehensive discussion covering:\n1. Financial alignment between system data and pitch deck (Turn 1)\n2. Valuation at 10-12x GOV ARR - aggressive but market-comparable (Turn 1)\n3. Critical execution risks around HDR expansion and technology scaling (Turn 2)\n4. Competitive failures in similar models (Reef, Kitchen United) (Turn 2)\n\n### Rationale for Conditional Proceed\n\n**Strengths:**\n- **Financial Consistency**: Perfect alignment between our data and their pitch deck builds credibility\n- **Strong Traction**: $407M GOV ARR is substantial proof of concept\n- **Differentiated Model**: FLASH technology + vertical integration addresses real market gaps\n- **Better Unit Economics**: 25% contribution margin vs. 15% industry average\n- **Quality Team**: Proven restaurant operators at the helm\n\n**Concerns:**\n- **Execution Risk**: 150+ location expansion by 2027 is extremely aggressive\n- **Capital Requirements**: $800M+ needed with high monthly burn\n- **Market Timing**: Coming after multiple ghost kitchen failures; investor sentiment cautious\n- **Unproven at Scale**: FLASH technology works at 12 locations but scale risk remains\n\n### Recommended Next Steps\n\n1. **Deep Dive on Technology** (Critical)\n   - Independent technical due diligence on FLASH system scalability\n   - Validate supply chain complexity management at 50+ location scale\n\n2. **Expansion Plan Stress Testing** (Critical)\n   - Request detailed city-by-city expansion timeline\n   - Validate real estate pipeline and site acquisition strategy\n   - Model scenarios at 75%, 50%, and 25% of planned expansion pace\n\n3. **Capital Structure Negotiation** (High Priority)\n   - Given execution risks, push for protective provisions\n   - Consider milestone-based tranched investment\n   - Negotiate board seat and quarterly reporting rights\n\n4. **Reference Calls** (High Priority)\n   - GV and other existing investors on execution to date\n   - Former CloudKitchens/Reef operators on scaling challenges\n\n### Deal Terms Guidance\n\n**From our system, current terms are:**\n- SAFE Note structure with 40% target IRR\n- $350M raise at $3.5B implied valuation\n\n**Recommended modifications:**\n- Structure as priced round (Series C) rather than SAFE for better protection\n- Target IRR of 45-50% given execution risk profile\n- Include performance milestones tied to HDR openings (e.g., reaching 30 locations by end of 2025)\n\n### Investment Committee Positioning\n\n**Risk/Return Profile**: High risk, high reward\n**Sector Alignment**: Strong (focus area for fund)\n**Differentiation**: Unique approach in crowded market\n**Timing**: Mixed - market cooling but opportunity differentiated\n\n**Bottom Line**: This is a \"conviction deal\" requiring belief in team execution and technology defensibility. Not suitable for risk-averse capital, but could be portfolio-defining winner if execution succeeds.",
    "sources": [
        {
            "type": "mcp",
            "domain": "deals",
            "tool": "get_opportunity_details"
        }
    ],
    "metadata": {
        "timestamp": "2024-12-27T11:15:00Z",
        "model": "gpt-4",
        "conversation_turns": 3,
        "conversation_summary": "Multi-turn analysis covering financial validation, risk assessment, competitive landscape, leading to investment recommendation with specific next steps"
    }
}
```

---

## Postman Collection Tips

### Headers

Set these headers for all requests:

| Header | Value |
|--------|-------|
| `Content-Type` | `application/json` |

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

### Test Script (Extract session_id)

Add this to the **Tests** tab to automatically capture `session_id` for follow-up requests:

```javascript
// Extract and save session_id from response
if (pm.response.code === 200) {
    var jsonData = pm.response.json();
    if (jsonData.session_id) {
        pm.environment.set("last_session_id", jsonData.session_id);
        console.log("Session ID saved: " + jsonData.session_id);
    }
}
```

### Pre-request Script (Using Variables)

Use this pattern in your request bodies with Postman variables:

```json
{
    "tenant_id": "{{tenant_id}}",
    "user_id": "{{user_id}}",
    "message": "Your question here",
    "type": "ask",
    "session_id": "{{last_session_id}}",
    "page_context": {
        "opportunity_id": "{{opportunity_id}}"
    }
}
```

---

## Quick Reference

### Request Types

| Scenario | MCP | RAG | Web | Multi-turn |
|----------|-----|-----|-----|------------|
| Simple Question | ❌ | ❌ | ❌ | ❌ |
| With Page Context | ✅ | ❌ | ❌ | ❌ |
| With Documents | ❌ | ✅ | ❌ | ❌ |
| With Web Search | ❌ | ❌ | ✅ | ❌ |
| Multi-turn Basic | ❌ | ❌ | ❌ | ✅ |
| Comprehensive Single | ✅ | ✅ | ✅ | ❌ |
| Comprehensive Multi | ✅ | ✅ | ✅ | ✅ |

### Key Fields

| Field | Required | Description |
|-------|----------|-------------|
| `tenant_id` | Yes | Tenant identifier |
| `user_id` | Yes | User identifier |
| `message` | Yes | User's question/request |
| `type` | Yes | Must be `"ask"` for Ask mode |
| `session_id` | No | Required for follow-up messages |
| `page_context` | No | Current page/screen context |
| `selected_docs` | No | Documents for RAG analysis |
| `enabled_mcps` | No | MCP domains to enable |
| `web_search_enabled` | No | Enable web search (boolean) |

---

## Testing Checklist

- [ ] Test simple question without any context
- [ ] Test with page context and MCP enabled
- [ ] Test with document selection (RAG)
- [ ] Test with web search enabled
- [ ] Test multi-turn conversation (2-3 turns)
- [ ] Test comprehensive request with all three sources (single-turn)
- [ ] Test comprehensive multi-turn conversation
- [ ] Verify session_id is returned and can be reused
- [ ] Verify sources are properly attributed in response
- [ ] Test error scenarios (missing fields, invalid session_id)

