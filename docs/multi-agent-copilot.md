# Multi-Agentic Copilot System Design (LangGraph)

## Objective

Design a **multi-agent, streaming AI copilot** using **LangGraph** that can:

- Answer contextual questions (**Ask mode**)
- Create, edit, and refine structured documents (**Create / Edit mode**)
- Support multiple document types:
  - Pre-screening reports
  - Investment memos
  - Custom reports
- Work **with or without templates**
- Integrate with:
  - Internal databases via **MCP servers**
  - A **RAG Gateway** backed by a vector database
  - **Web search** (optional / gated)
- Operate with **human-in-the-loop clarification**
- Provide **section-level source traceability**
- Stream **real-time progress updates** to the user

---

## Design Principles

1. **Plan before execution**  
   The system must always generate and confirm a plan before writing content.

2. **Human-in-the-loop by default**  
   Ambiguity triggers clarification instead of assumptions.

3. **Composable agents**  
   Each agent has a focused responsibility and is reusable.

4. **Tool-aware reasoning**  
   Agents explicitly decide *which tools to call and why*.

5. **Traceability & auditability**  
   Every section must retain references to its data sources.

6. **Streaming-first UX**  
   Users see progress, decisions, and checkpoints in real time.

---

## High-Level Flow Overview

User Request
↓
Intent & Context Analysis
↓
Clarification (if needed)
↓
Planning
↓
User Confirmation
↓
Data Retrieval (DB / RAG / Web)
↓
Synthesis & Insights
↓
Template Handling
↓
Section-wise Generation
↓
Review & Coherence Check
↓
Source Attribution
↓
Final Output + Streaming Updates


---

## Core Agents

### 1. Orchestrator / Supervisor Agent
- Owns the LangGraph state machine
- Controls transitions, retries, and termination
- Decides when to pause for user input
- Emits streaming lifecycle events

---

### 2. Intent & Context Analyzer

**Inputs**
- User prompt
- Frontend / page context (e.g., deal page, opportunity ID)
- Optional system metadata

**Responsibilities**
- Classify request:
  - Ask / Create / Edit / Extend
- Identify document type
- Detect presence of templates
- Identify required entities (deal, client, strategy)
- Detect missing or ambiguous inputs

**Outputs**
- Structured intent summary
- List of clarification questions (if any)

---

### 3. Clarification Agent (Human-in-the-Loop)

Triggered only when inputs are incomplete or ambiguous.

Examples:
- “Should we use an existing template?”
- “Which opportunity should this report be based on?”
- “What depth or audience is this document for?”

Behavior:
- Pause execution
- Stream clarification request
- Await user response
- Update graph state and resume

---

### 4. Planning Agent

Generates a **formal execution plan** before any data access or writing.

**Plan includes**
- Section outline
- Data requirements per section
- Tool usage plan:
  - MCP DB calls
  - RAG Gateway queries
  - Web search (if enabled)
- Template strategy:
  - Use existing
  - Modify existing
  - Generate new
- Expected review checkpoints

**Output**
- A structured plan sent to the user for approval

---

### 5. User Confirmation Gate

Execution **must not proceed** without explicit confirmation.

Possible outcomes:
- Approved → continue
- Requested changes → re-plan
- Cancelled → terminate safely

---

## Data & Knowledge Acquisition

### 6. MCP Data Retrieval Agent

Interfaces with internal systems via MCP servers.

Used for:
- Opportunity status
- Financial metrics
- Client / asset metadata
- Historical data

Returns:
- Structured data payload
- Metadata (source system, timestamps, entity IDs)

Constraints:
- Read-only
- Tenant-isolated

---

### 7. RAG Gateway Agent

Retrieves unstructured content from the vector database.

Capabilities:
- Section-specific queries
- Multi-document aggregation
- Chunk-level metadata capture:
  - Document ID
  - Chunk ID
  - Section/page reference
  - Similarity score

---

### 8. Web Search Agent (Optional)

Enabled only when explicitly allowed.

Used for:
- Market context
- Benchmarks
- Public comparables
- Regulatory references

Returns:
- URLs
- Extracted snippets
- Retrieval timestamps

---

## Content Construction

### 9. Synthesis & Insight Agent

Combines:
- MCP structured data
- RAG unstructured content
- Web data (if enabled)

Responsibilities:
- Normalize terminology
- Identify gaps or contradictions
- Generate insights (not just summaries)
- Flag weak evidence

---

### 10. Template Manager Agent

Handles all template logic.

Modes:
1. Existing template → populate
2. Template adaptation → extend or prune
3. Template generation → create from scratch

Outputs:
- Final template schema
- Section-to-data mapping

---

### 11. Section Writer Agents (Parallelizable)

Each section is generated independently.

For each section:
- Consume only relevant data
- Maintain tone & consistency
- Attach source references
- Stream intermediate drafts

---

### 12. Review & Coherence Agent

Final validation pass.

Checks:
- Cross-section consistency
- Logical flow
- Terminology alignment
- Redundancy
- Missing citations

---

## Source Attribution

### 13. Source Mapping Agent

Creates a structured source ledger.

For each section:
- Source type (DB / RAG / Web)
- Source identifiers
- Chunk references
- Confidence scores

Returned alongside the final document.

---

## Streaming Event Model

The system emits real-time events such as:

- `intent_detected`
- `clarification_required`
- `planning_started`
- `awaiting_user_confirmation`
- `fetching_db_data`
- `fetching_rag_data`
- `writing_section.<section_name>`
- `review_in_progress`
- `completed`

This ensures transparency, debuggability, and trust.

---

## Editing & Iteration Flow

For edit requests:
- Identify impacted sections
- Re-fetch data only if required
- Preserve unaffected sections
- Re-emit updated sources
- Maintain version history

---

## Final Output

The final response includes:
1. Generated document
2. Section-wise source references
3. Execution summary
4. Optional next actions (export, shorten, reuse template)

---

## End State

The system delivers:
- A traceable, auditable document
- Continuous user interaction
- Clear separation of planning, retrieval, and generation
- A reusable multi-agent architecture aligned with LangGraph

---
