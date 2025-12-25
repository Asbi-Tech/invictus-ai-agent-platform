# Invictus AI Copilot Agents & MCP Platform — Implementation Plan (Updated)

## Context

Invictus AI is an AI-native wealth management platform with multiple modules:

- Deals  
- Client Portal  
- CRM  
- Risk & Planning  
- Admin  

Your team is building **reusable AI components** across all modules.

Already built:

1. **Document Intelligence**: ingestion pipeline that stores + vectorizes complex documents (visuals + text) into **Azure AI Search** (vector DB).
2. **RAG Gateway**: multi-endpoint service that accepts requests from multiple modules and, using `tenant_id` + document selectors, retrieves and reasons over vector stores.

Next: build **modular Copilot Agents** that can be used across modules, initially simple, and evolving toward richer MCP-based tool ecosystems.

---

## Requirements Summary

Copilot capabilities:

- Q&A over module/page context + selected documents
- Generate content (custom reports, strategy docs, memos)
- Edit existing reports/strategy docs

Copilot can access:

- **Vector DB** via your existing RAG Gateway (on user-selected docs)
- **MCP tools** (domain services that read from various databases/systems)
- **Internet search** via Tavily (**only when enabled**)

Engineering requirements:

- Build with **LangGraph + Python + FastAPI**
- MCP servers implemented with **FastMCP**
- Deploy on **Azure**
- **Session memory** + state persistence per session (use **Cosmos DB**)
- **Streaming** output and “agent activity timeline” to FE
- **Human-in-the-loop (HITL)** for ambiguity and any sensitive actions
- For now:
  - MCP DB connectivity can be **password-based authentication** (read-only)
  - Security/tenant isolation can be **simplified** (password-based), but still keep minimal guardrails

---

## 1) Target Architecture (Updated)

### Services

1. **Copilot Agent API (FastAPI + LangGraph)**
   - Single entrypoint for all modules initially
   - Handles:
     - Authentication (simple for now)
     - Tenant isolation (basic enforcement)
     - Session memory & checkpointing (Cosmos DB)
     - Streaming (SSE)
     - HITL pause/resume
     - Tool orchestration & logging

2. **MCP Tool Layer (FastMCP servers)**
   - Separate microservices by domain:
     - opportunities, clients, risk, reporting, admin-policy, etc.
   - For now: **read-only tools**
   - Connect to existing DBs/services using **password-based authentication**
   - Tools should still enforce:
     - `tenant_id` filtering (server-side)
     - minimum request validation
     - auditing

3. **RAG Gateway (existing)**
   - Treated as a tool in the agent
   - Used only when docs are selected (or retrieval is needed)

4. **Internet Search (Tavily)**
   - Optional tool, enabled per request or tenant config
   - Logged and cited, can be disabled by default

### Storage (Updated)

- **Cosmos DB**: session state, checkpoints, conversation history, tool event summaries, HITL requests/responses  
- **Blob Storage** (optional but recommended): generated artifacts (memos, strategy drafts, exported markdown)

> If you want to stay “Cosmos-only” initially, you can store artifacts in Cosmos as well, but Blob is better for large documents and versioning.

---

## 2) “Show what’s happening” to the user (Without exposing raw chain-of-thought)

Do not stream raw model chain-of-thought. Instead, stream **structured progress events** that FE can display as a timeline.

Recommended event categories:

- `status`: current stage (e.g., `gathering_context`, `retrieving_docs`, `drafting_report`)
- `tool_call_start`: tool name + sanitized input
- `tool_call_result`: sanitized output + latency + citations
- `assistant_delta`: incremental text tokens for streaming the final response
- `artifact_update`: progress per section (e.g., “Drafting Section 2/5”)
- `hitl_request`: questions/options for the user
- `final`: final response + metadata

This gives transparency and trust while staying safe.

---

## 3) LangGraph Design (MVP that scales)

### State model (start simple)

Define a typed `AgentState` containing:

- `tenant_id`, `user_id`, `module_id`
- `session_id`
- `conversation` (messages)
- `page_context` (screen name + entity ids)
- `selected_docs` (doc ids or sets allowed)
- `tool_policy` (internet enabled? which MCP domains enabled?)
- `working_memory` (session facts summary)
- `artifacts` (draft ids + storage pointers)
- `last_tool_results` (avoid repeated calls)

### MVP graph nodes

1. **ingest_context**
   - validate payload
   - normalize module/entity context
   - load tenant tool policy (simple initially)

2. **route_intent**
   - classify: Q&A vs Generate vs Edit vs Summarize vs Compare
   - decide candidate tools needed

3. **gather_context**
   - call MCP read tools (entity snapshots: opportunity, client, risk)
   - call RAG Gateway for doc retrieval (only when needed)

4. **draft_or_answer**
   - compose response or create a structured report plan
   - ensure citations are attached when using retrieval/search

5. **hitl_gate**
   - interrupt if:
     - missing required inputs (timeframe, audience, benchmark)
     - user must choose among options
     - internet search is required but not enabled

6. **finalize**
   - persist checkpoint + session summary (Cosmos DB)
   - store artifacts if generated (Cosmos or Blob)
   - stream final output + references

### Scaling later (no need day 1)

- Subgraphs: `retrieval_subgraph`, `report_generation_subgraph`, `edit_subgraph`
- Quality checks: citation completeness, confidence scoring
- Tool budget limits & retry rules
- Partial caching of repeated entity snapshots

---

## 4) MCP Tool Strategy (Password-based DB auth, read-only)

### Principles

- Domain-based MCP servers (avoid mega-server)
- Small, typed tools
- **Read-only** first (no writes)
- Enforce tenant filtering server-side

### Suggested MCP servers (initial)

1. `mcp-opportunities`
   - `get_opportunity(opportunity_id, tenant_id)`
   - `get_opportunity_kpis(opportunity_id, tenant_id)`
   - `list_opportunity_documents(opportunity_id, tenant_id)`

2. `mcp-clients`
   - `get_client(client_id, tenant_id)`
   - `get_client_relationships(client_id, tenant_id)`
   - `get_client_portfolio_snapshot(client_id, tenant_id)`

3. `mcp-risk-planning`
   - `get_ips(strategy_id, tenant_id)`
   - `get_ipq(client_id, tenant_id)`
   - `get_risk_profile(client_id, tenant_id)`

4. `mcp-reporting` (read-only initially)
   - `get_report_template(template_id, tenant_id)`
   - `get_existing_report(report_id, tenant_id)`

5. `mcp-admin-policy`
   - `get_tenant_tool_policy(tenant_id)`
   - `get_user_permissions(user_id, tenant_id)`

### DB connection (Updated)

- For now, use password-based auth for DB connectivity.
- Keep credentials in environment variables (local) and **Azure Key Vault** (cloud).
- Create a simple connection factory per MCP server that:
  - opens pooled connection
  - enforces read-only transactions if DB supports it
  - includes per-request tenant filter requirements

---

## 5) Memory, Session State, and Artifacts (Cosmos DB)

### Session memory (must-have)

Use LangGraph checkpointing persisted to **Cosmos DB**:

- key by `(tenant_id, session_id)`
- store:
  - last graph state snapshot
  - conversation window
  - summarized older turns
  - last tool results summary
  - HITL pending requests (if any)

### Summarization policy

To keep Cosmos payloads small:

- Keep last N turns verbatim (e.g., last 10)
- Summarize older turns into a single `session_summary`
- Summarize tool outputs into `tool_summary` (store full tool results only if needed)

### Artifacts

When generating a memo/report:

- store content as markdown
- keep:
  - `artifact_id`, version, created_by, timestamps
  - citations bundle (doc refs + chunk ids + sources)

Storage options:
- **Cosmos only** (fast to start)
- Later: **Blob Storage** for larger artifacts + version history

---

## 6) Streaming Design (SSE)

### Endpoints

- `POST /v1/copilot/chat` (non-stream) → final response
- `POST /v1/copilot/stream` (SSE) → emits events
- `POST /v1/copilot/resume` → continue after HITL

### SSE event schema (recommended)

- `status`
- `tool_call_start`
- `tool_call_result`
- `assistant_delta`
- `artifact_update`
- `hitl_request`
- `final`

This enables FE to show a live activity feed and render output as it’s produced.

---

## 7) Human-in-the-loop (HITL)

Use HITL interrupts for:

1. **Missing inputs**
   - timeframe, currency, benchmark, audience type, doc scope

2. **Ambiguity**
   - “Which opportunity?” if multiple matches
   - “Do you want performance YTD or last 12 months?”

3. **Internet Search gate**
   - if the agent determines external search is required but not enabled

Implementation:
- graph pauses and returns a `hitl_request` with:
  - `question`
  - `options` (optional)
  - `required_fields` (optional)
- FE calls `/resume` with user answers

---

## 8) Security & Tenant Isolation (Simplified for now)

Given your current constraints, keep security simple:

- Password-based credentials for DB connectivity (read-only)
- `tenant_id` always required for:
  - agent sessions
  - MCP tool calls
  - RAG gateway calls

Minimum guardrails to keep even in MVP:

- MCP servers enforce tenant filters server-side (never trust FE)
- Audit log tool usage (tenant/user/session)
- Redact secrets from logs
- Internet search disabled by default unless enabled per request

> Later you can upgrade to Managed Identity + Entra ID auth, but the system will already be structured correctly.

---

## 9) Repo Structure (pip-based)

You’re using **pip** (not uv). Below structure keeps monorepo scalable, while remaining pip-friendly.

```
invictus-ai-copilot/
  README.md
  .env.example
  .gitignore

  requirements/
    base.txt
    dev.txt
    agent_api.txt
    mcp_common.txt
    mcp_opportunities.txt
    mcp_clients.txt
    mcp_risk_planning.txt
    mcp_admin_policy.txt
    mcp_reporting.txt

  apps/
    agent_api/
      src/agent_api/
        main.py
        api/
          routes.py
          schemas.py
        auth/
        streaming/
        observability/
      tests/
      requirements.txt          # can reference ../requirements/agent_api.txt

    mcp_servers/
      opportunities/
        src/mcp_opportunities/
          server.py
          tools.py
          db.py
          schemas.py
        tests/
        requirements.txt        # refs ../requirements/mcp_opportunities.txt
      clients/
      risk_planning/
      admin_policy/
      reporting/

  packages/
    agent_core/
      src/agent_core/
        graph/
          base_graph.py
          nodes/
          subgraphs/
        state/
          models.py
        tools/
          rag_gateway.py
          tavily_search.py
          mcp_client.py
        policy/
          tool_policy.py
          tenant_policy.py
        memory/
          cosmos_checkpointer.py
          summarizer.py
        eval/
          golden_tests.py
      tests/
      pyproject.toml            # optional for packaging, even with pip installs

    mcp_common/
      src/mcp_common/
        auth.py
        models/
        telemetry.py
      tests/

    common/
      src/common/
        config.py
        logging.py
        errors.py

  infra/
    bicep-or-terraform/
      container-apps/
      key-vault/
      cosmosdb/
      app-insights/

  docs/
    architecture.md
    tool-catalog.md
    streaming-events.md
    security.md
    runbooks.md

  scripts/
    local_dev.sh
    seed_dev_data.py
```

### pip install approach

- Use per-service `requirements.txt` that includes shared requirements via `-r`.
- For local dev, install packages in editable mode:
  - `pip install -e packages/agent_core`
  - `pip install -e packages/mcp_common`

---

## 10) Step-by-step Implementation Plan (Updated)

### Phase 0 — Repo & CI Foundation (Days 1–3)

- Create repo scaffolding (structure above)
- Add `requirements/` split files
- Add lint/test tooling:
  - ruff, mypy, pytest
- Add CI workflow:
  - install deps (pip)
  - run lint + typecheck + unit tests

**Deliverable:** green build, consistent package layout.

---

### Phase 1 — MVP Copilot + Streaming + Cosmos Memory (Week 1)

**Goal:** Q&A using entity context + selected docs, with streaming and session persistence.

1. Build `packages/agent_core`:
   - `AgentState`
   - Graph MVP: ingest → route → gather_context → answer → finalize
   - Cosmos checkpointer for session state

2. Implement tool wrappers:
   - RAG Gateway client wrapper (your existing service)
   - Basic MCP client wrapper (HTTP)

3. Build `apps/agent_api`:
   - SSE stream endpoint (`/v1/copilot/stream`)
   - non-stream endpoint (`/v1/copilot/chat`)
   - session create/resume + Cosmos persistence

4. Build first MCP server (`mcp-opportunities`):
   - password-based DB auth
   - read tools for opportunity snapshot + KPIs

**Deliverable:** Deals module can ask:
- “Summarize this opportunity + key risks”
- “What do the selected docs say about fees and lockup?”

…and see a live activity feed.

---

### Phase 2 — Content Generation + Artifact Storage (Week 2)

**Goal:** Generate memos/strategy docs and store them for reuse/editing.

- Add report generation subgraph:
  - outline → draft sections → citations → final markdown artifact
- Store artifacts:
  - Cosmos document per artifact + versioning (or Blob optional)
- Add edit flow:
  - “Rewrite section 2 with a more formal tone”
  - save new artifact version

**Deliverable:** “Generate Investment Memo v1” + “Revise existing report”.

---

### Phase 3 — HITL + Tool Governance (Week 3)

**Goal:** safer and fewer wrong assumptions.

- Add HITL interruptions:
  - missing inputs
  - ambiguous entity selection
  - internet search gate
- Add tenant tool policy:
  - enable/disable Tavily
  - allow/deny MCP domains
  - retrieval limits
- Add audit log entries:
  - per tool call: tenant/user/session/tool/latency

**Deliverable:** agent pauses and asks for clarification, resumes cleanly.

---

### Phase 4 — Expand MCP Ecosystem (Week 4–6)

**Goal:** reuse across CRM / Risk / Client Portal.

- Add MCP servers:
  - clients, risk-planning, reporting, admin-policy
- Standardize:
  - request/response schemas (shared in `mcp_common`)
  - error codes
  - pagination patterns
- Add integration tests:
  - contract tests for MCP tools
  - golden path flows per module

**Deliverable:** Same copilot works in multiple modules with different enabled tools.

---

### Phase 5 — Production Hardening (Ongoing)

- Observability: traces + metrics + dashboards
- Reliability: retries/backoff, circuit breakers, caching
- Evaluation: golden tests, citation checks, regression suite
- Security upgrades later:
  - replace passwords with Managed Identity/Entra
  - private networking + stricter policies

---

## 11) Azure Deployment Recommendation (Pragmatic)

Best default: **Azure Container Apps**

- Deploy:
  - agent_api as one container app
  - each MCP server as separate container app
- Use:
  - Key Vault for passwords/secrets
  - App Insights for logs + metrics
  - VNet integration where needed

Alternative (simpler): Azure App Service (if networking requirements are minimal)

---

## 12) Build Order (Fastest path to value)

1. Agent API + SSE streaming + Cosmos checkpointing
2. MCP Opportunities (read-only, password DB auth)
3. RAG Gateway tool integration
4. Memo generation + artifact storage
5. HITL for ambiguity + Tavily gating

This delivers a working copilot in Deals quickly while keeping the platform modular for future expansion.
