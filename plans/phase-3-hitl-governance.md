# Phase 3: Human-in-the-Loop (HITL) + Tool Governance

## Objectives

- Implement HITL interruption mechanism for ambiguity and missing inputs
- Add `/resume` endpoint for continuing after HITL
- Create tenant tool policy system (enable/disable tools per tenant)
- Add comprehensive audit logging for tool calls
- Integrate Tavily internet search with gating

## Prerequisites

- Phase 2 completed (content generation, artifact storage)
- Agent API running with streaming
- Cosmos DB collections set up

---

## Implementation Tasks

### Task 3.1: Define HITL Models

**packages/agent_core/src/agent_core/state/hitl.py**
```python
"""Human-in-the-loop models and utilities."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class HITLType(str, Enum):
    """Types of HITL interrupts."""
    MISSING_INPUT = "missing_input"
    AMBIGUOUS_ENTITY = "ambiguous_entity"
    CONFIRMATION_REQUIRED = "confirmation_required"
    INTERNET_SEARCH_GATE = "internet_search_gate"
    TOOL_PERMISSION = "tool_permission"
    CUSTOM = "custom"


class HITLOption(BaseModel):
    """An option for the user to select."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    label: str
    value: Any
    description: str | None = None


class HITLField(BaseModel):
    """A field the user needs to provide."""
    name: str
    label: str
    field_type: str = "text"  # text, number, date, select
    required: bool = True
    options: list[HITLOption] | None = None  # For select type
    default_value: Any = None
    placeholder: str | None = None


class HITLRequest(BaseModel):
    """A request for human input."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    hitl_type: HITLType
    title: str
    message: str
    options: list[HITLOption] | None = None
    fields: list[HITLField] | None = None
    context: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None


class HITLResponse(BaseModel):
    """Response from the user for a HITL request."""
    request_id: str
    selected_option_id: str | None = None
    field_values: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class HITLState(BaseModel):
    """HITL state within agent state."""
    pending_request: HITLRequest | None = None
    history: list[tuple[HITLRequest, HITLResponse]] = Field(default_factory=list)
    is_paused: bool = False


def create_missing_input_request(
    missing_fields: list[str],
    context: dict[str, Any] | None = None,
) -> HITLRequest:
    """Create a HITL request for missing inputs."""
    field_labels = {
        "timeframe": "Time Period",
        "currency": "Currency",
        "benchmark": "Benchmark",
        "audience": "Target Audience",
        "doc_scope": "Document Scope",
    }

    fields = [
        HITLField(
            name=field,
            label=field_labels.get(field, field.replace("_", " ").title()),
            field_type="text",
            required=True,
        )
        for field in missing_fields
    ]

    return HITLRequest(
        hitl_type=HITLType.MISSING_INPUT,
        title="Additional Information Required",
        message="Please provide the following information to continue:",
        fields=fields,
        context=context or {},
    )


def create_ambiguous_entity_request(
    entity_type: str,
    matches: list[dict[str, Any]],
) -> HITLRequest:
    """Create a HITL request for ambiguous entity selection."""
    options = [
        HITLOption(
            id=str(m.get("id", i)),
            label=m.get("name", f"Option {i+1}"),
            value=m.get("id"),
            description=m.get("description", ""),
        )
        for i, m in enumerate(matches)
    ]

    return HITLRequest(
        hitl_type=HITLType.AMBIGUOUS_ENTITY,
        title=f"Multiple {entity_type.title()}s Found",
        message=f"Which {entity_type} did you mean?",
        options=options,
        context={"entity_type": entity_type, "matches": matches},
    )


def create_internet_search_gate_request(
    search_query: str,
) -> HITLRequest:
    """Create a HITL request for internet search permission."""
    return HITLRequest(
        hitl_type=HITLType.INTERNET_SEARCH_GATE,
        title="Internet Search Required",
        message=f"To answer your question, I need to search the internet for: '{search_query}'. Do you want to allow this?",
        options=[
            HITLOption(id="allow", label="Allow Search", value=True),
            HITLOption(id="deny", label="Don't Search", value=False),
        ],
        context={"search_query": search_query},
    )
```

---

### Task 3.2: Define Tool Policy Models

**packages/agent_core/src/agent_core/policy/tool_policy.py**
```python
"""Tool policy configuration and enforcement."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ToolAccessLevel(str, Enum):
    """Access levels for tools."""
    FULL = "full"  # Can use without restrictions
    GATED = "gated"  # Requires HITL confirmation
    DISABLED = "disabled"  # Cannot use


class ToolConfig(BaseModel):
    """Configuration for a specific tool."""
    tool_name: str
    access_level: ToolAccessLevel = ToolAccessLevel.FULL
    max_calls_per_session: int | None = None
    requires_confirmation: bool = False
    allowed_parameters: dict[str, Any] | None = None  # Parameter restrictions


class MCPDomainConfig(BaseModel):
    """Configuration for an MCP domain."""
    domain: str
    enabled: bool = True
    tools: list[ToolConfig] = Field(default_factory=list)


class TenantToolPolicy(BaseModel):
    """Tool policy for a tenant."""
    tenant_id: str
    policy_version: int = 1

    # Global settings
    internet_search_enabled: bool = False
    internet_search_requires_confirmation: bool = True
    rag_enabled: bool = True
    max_tool_calls_per_session: int = 20
    max_rag_results: int = 10

    # MCP domain configurations
    mcp_domains: list[MCPDomainConfig] = Field(default_factory=list)

    # Audit settings
    audit_enabled: bool = True
    audit_level: str = "full"  # minimal, standard, full

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def is_tool_enabled(self, domain: str, tool_name: str) -> bool:
        """Check if a specific tool is enabled."""
        for domain_config in self.mcp_domains:
            if domain_config.domain == domain:
                if not domain_config.enabled:
                    return False
                for tool in domain_config.tools:
                    if tool.tool_name == tool_name:
                        return tool.access_level != ToolAccessLevel.DISABLED
                # Tool not explicitly configured, use domain default
                return domain_config.enabled
        # Domain not configured, enabled by default
        return True

    def requires_confirmation(self, domain: str, tool_name: str) -> bool:
        """Check if a tool requires confirmation."""
        for domain_config in self.mcp_domains:
            if domain_config.domain == domain:
                for tool in domain_config.tools:
                    if tool.tool_name == tool_name:
                        return tool.requires_confirmation
        return False


class DefaultPolicies:
    """Default policy configurations."""

    @staticmethod
    def get_default_policy(tenant_id: str) -> TenantToolPolicy:
        """Get the default policy for a tenant."""
        return TenantToolPolicy(
            tenant_id=tenant_id,
            internet_search_enabled=False,
            internet_search_requires_confirmation=True,
            rag_enabled=True,
            mcp_domains=[
                MCPDomainConfig(
                    domain="opportunities",
                    enabled=True,
                    tools=[
                        ToolConfig(tool_name="get_opportunity", access_level=ToolAccessLevel.FULL),
                        ToolConfig(tool_name="get_opportunity_kpis", access_level=ToolAccessLevel.FULL),
                        ToolConfig(tool_name="list_opportunity_documents", access_level=ToolAccessLevel.FULL),
                    ],
                ),
                MCPDomainConfig(
                    domain="clients",
                    enabled=True,
                ),
                MCPDomainConfig(
                    domain="risk_planning",
                    enabled=True,
                ),
            ],
        )
```

---

### Task 3.3: Build Policy Store

**packages/agent_core/src/agent_core/policy/tenant_policy.py**
```python
"""Tenant policy storage and retrieval."""

from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError

from agent_core.policy.tool_policy import TenantToolPolicy, DefaultPolicies
from common.logging import get_logger

logger = get_logger(__name__)


class TenantPolicyStore:
    """Store and retrieve tenant policies from Cosmos DB."""

    def __init__(
        self,
        endpoint: str,
        key: str,
        database_name: str,
        container_name: str = "policies",
    ):
        self.client = CosmosClient(endpoint, credential=key)
        self.database = self.client.get_database_client(database_name)
        self.container = self.database.get_container_client(container_name)

    async def get_policy(self, tenant_id: str) -> TenantToolPolicy:
        """Get the policy for a tenant, or return default."""
        try:
            item = self.container.read_item(
                item=f"policy:{tenant_id}",
                partition_key=tenant_id,
            )
            return TenantToolPolicy(**item)
        except CosmosResourceNotFoundError:
            logger.info("No policy found for tenant, using default", tenant_id=tenant_id)
            return DefaultPolicies.get_default_policy(tenant_id)

    async def save_policy(self, policy: TenantToolPolicy) -> TenantToolPolicy:
        """Save a tenant policy."""
        doc = {
            "id": f"policy:{policy.tenant_id}",
            "tenant_id": policy.tenant_id,
            **policy.model_dump(),
        }
        self.container.upsert_item(doc)
        logger.info("Saved policy", tenant_id=policy.tenant_id, version=policy.policy_version)
        return policy


# Simple in-memory cache for policies
_policy_cache: dict[str, TenantToolPolicy] = {}


async def get_tenant_policy(
    tenant_id: str,
    store: TenantPolicyStore | None = None,
) -> TenantToolPolicy:
    """Get tenant policy with caching."""
    if tenant_id in _policy_cache:
        return _policy_cache[tenant_id]

    if store:
        policy = await store.get_policy(tenant_id)
    else:
        policy = DefaultPolicies.get_default_policy(tenant_id)

    _policy_cache[tenant_id] = policy
    return policy
```

---

### Task 3.4: Build Audit Logging

**packages/agent_core/src/agent_core/observability/audit.py**
```python
"""Audit logging for tool calls and agent actions."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from common.logging import get_logger

logger = get_logger(__name__)


class AuditEventType(str, Enum):
    """Types of audit events."""
    TOOL_CALL = "tool_call"
    RAG_QUERY = "rag_query"
    INTERNET_SEARCH = "internet_search"
    HITL_REQUEST = "hitl_request"
    HITL_RESPONSE = "hitl_response"
    ARTIFACT_CREATED = "artifact_created"
    ARTIFACT_MODIFIED = "artifact_modified"
    SESSION_STARTED = "session_started"
    SESSION_ENDED = "session_ended"
    ERROR = "error"


class AuditEvent(BaseModel):
    """An audit event record."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: AuditEventType
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # Context
    tenant_id: str
    user_id: str
    session_id: str

    # Event details
    action: str
    resource: str | None = None
    resource_id: str | None = None

    # Request/Response
    input_summary: str | None = None
    output_summary: str | None = None
    input_hash: str | None = None  # For sensitive data

    # Performance
    latency_ms: float | None = None
    success: bool = True
    error_message: str | None = None

    # Additional metadata
    metadata: dict[str, Any] = Field(default_factory=dict)


class AuditLogger:
    """Audit logger that writes to structured logs and optionally to storage."""

    def __init__(
        self,
        cosmos_client=None,
        database_name: str | None = None,
        container_name: str = "audit_logs",
    ):
        self._cosmos_container = None
        if cosmos_client and database_name:
            database = cosmos_client.get_database_client(database_name)
            self._cosmos_container = database.get_container_client(container_name)

    async def log(self, event: AuditEvent) -> None:
        """Log an audit event."""
        # Always log to structured logger
        logger.info(
            "audit_event",
            event_id=event.id,
            event_type=event.event_type.value,
            tenant_id=event.tenant_id,
            user_id=event.user_id,
            session_id=event.session_id,
            action=event.action,
            resource=event.resource,
            success=event.success,
            latency_ms=event.latency_ms,
        )

        # Optionally persist to Cosmos DB
        if self._cosmos_container:
            try:
                doc = {
                    "id": event.id,
                    "partition_key": event.tenant_id,
                    **event.model_dump(),
                }
                self._cosmos_container.upsert_item(doc)
            except Exception as e:
                logger.error("Failed to persist audit event", error=str(e))

    async def log_tool_call(
        self,
        tenant_id: str,
        user_id: str,
        session_id: str,
        tool_name: str,
        input_summary: str,
        output_summary: str,
        latency_ms: float,
        success: bool,
        error_message: str | None = None,
    ) -> None:
        """Log a tool call."""
        event = AuditEvent(
            event_type=AuditEventType.TOOL_CALL,
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            action="tool_call",
            resource=tool_name,
            input_summary=input_summary[:500] if input_summary else None,
            output_summary=output_summary[:500] if output_summary else None,
            latency_ms=latency_ms,
            success=success,
            error_message=error_message,
        )
        await self.log(event)

    async def log_hitl_request(
        self,
        tenant_id: str,
        user_id: str,
        session_id: str,
        hitl_type: str,
        request_id: str,
    ) -> None:
        """Log a HITL request."""
        event = AuditEvent(
            event_type=AuditEventType.HITL_REQUEST,
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            action="hitl_request",
            resource=hitl_type,
            resource_id=request_id,
        )
        await self.log(event)

    async def log_hitl_response(
        self,
        tenant_id: str,
        user_id: str,
        session_id: str,
        request_id: str,
        response_summary: str,
    ) -> None:
        """Log a HITL response."""
        event = AuditEvent(
            event_type=AuditEventType.HITL_RESPONSE,
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            action="hitl_response",
            resource_id=request_id,
            output_summary=response_summary,
        )
        await self.log(event)


# Global audit logger instance
_audit_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    """Get the global audit logger."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


def initialize_audit_logger(
    cosmos_client=None,
    database_name: str | None = None,
) -> AuditLogger:
    """Initialize the global audit logger with Cosmos DB."""
    global _audit_logger
    _audit_logger = AuditLogger(
        cosmos_client=cosmos_client,
        database_name=database_name,
    )
    return _audit_logger
```

---

### Task 3.5: Build Tavily Search Tool

**packages/agent_core/src/agent_core/tools/tavily_search.py**
```python
"""Tavily internet search tool with gating."""

from datetime import datetime
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel
from tavily import TavilyClient

from agent_core.state.hitl import HITLRequest, create_internet_search_gate_request
from common.config import get_settings
from common.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class TavilySearchResult(BaseModel):
    """A single search result."""
    title: str
    url: str
    content: str
    score: float


class TavilySearchOutput(BaseModel):
    """Output from Tavily search."""
    query: str
    results: list[TavilySearchResult]
    answer: str | None = None


async def search_internet(
    query: str,
    max_results: int = 5,
    include_answer: bool = True,
) -> TavilySearchOutput:
    """
    Search the internet using Tavily.

    Note: This should only be called after HITL approval if gating is enabled.
    """
    if not settings.tavily_api_key:
        logger.warning("Tavily API key not configured")
        return TavilySearchOutput(
            query=query,
            results=[],
            answer="Internet search is not configured.",
        )

    client = TavilyClient(api_key=settings.tavily_api_key)

    try:
        response = client.search(
            query=query,
            max_results=max_results,
            include_answer=include_answer,
            search_depth="advanced",
        )

        results = [
            TavilySearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                content=r.get("content", ""),
                score=r.get("score", 0.0),
            )
            for r in response.get("results", [])
        ]

        return TavilySearchOutput(
            query=query,
            results=results,
            answer=response.get("answer"),
        )

    except Exception as e:
        logger.error("Tavily search failed", error=str(e))
        return TavilySearchOutput(
            query=query,
            results=[],
            answer=f"Search failed: {str(e)}",
        )


@tool
async def web_search(
    query: str,
    max_results: int = 5,
) -> str:
    """
    Search the internet for current information.

    Use this tool when you need up-to-date information that may not be in the documents,
    such as current market data, recent news, or real-time information.

    Note: This tool requires user approval before use.

    Args:
        query: The search query
        max_results: Maximum number of results to return

    Returns:
        Search results with sources
    """
    result = await search_internet(query, max_results)

    if not result.results:
        return result.answer or "No results found."

    output_parts = []

    if result.answer:
        output_parts.append(f"Summary: {result.answer}\n")

    output_parts.append(f"Found {len(result.results)} results:\n")

    for i, r in enumerate(result.results, 1):
        output_parts.append(f"\n[{i}] {r.title}")
        output_parts.append(f"    Source: {r.url}")
        output_parts.append(f"    {r.content[:200]}...")

    return "\n".join(output_parts)


def check_requires_internet_search(
    query: str,
    context: dict[str, Any],
) -> tuple[bool, str | None]:
    """
    Check if a query requires internet search.

    Returns (requires_search, search_query)
    """
    query_lower = query.lower()

    # Keywords that suggest internet search is needed
    internet_keywords = [
        "current", "latest", "recent", "today",
        "news", "market", "price", "rate",
        "2024", "2025",  # Recent years
        "what is the current", "what are the latest",
    ]

    for keyword in internet_keywords:
        if keyword in query_lower:
            # Context might have the answer, check first
            if not context.get("rag_results"):
                return True, query

    return False, None
```

---

### Task 3.6: Build HITL Node

**packages/agent_core/src/agent_core/graph/nodes/hitl_gate.py**
```python
"""HITL gate node for handling interruptions."""

from typing import Any

from langchain_core.messages import HumanMessage

from agent_core.state.models import AgentState, IntentType
from agent_core.state.hitl import (
    HITLRequest,
    HITLState,
    HITLType,
    create_missing_input_request,
    create_ambiguous_entity_request,
    create_internet_search_gate_request,
)
from agent_core.tools.tavily_search import check_requires_internet_search
from agent_core.policy.tenant_policy import get_tenant_policy
from agent_core.observability.audit import get_audit_logger
from common.logging import get_logger

logger = get_logger(__name__)


# Required fields for different intents
REQUIRED_FIELDS = {
    IntentType.GENERATE: ["audience"],  # Audience is often needed for reports
    IntentType.COMPARE: ["timeframe"],  # Timeframe needed for comparisons
}


async def hitl_gate(state: AgentState) -> dict:
    """
    Check if HITL interruption is needed.

    Checks for:
    1. Missing required inputs
    2. Ambiguous entity selection
    3. Internet search gate
    """
    audit_logger = get_audit_logger()

    # Skip if already paused or has pending request
    if state.hitl_pending:
        return {}

    # Get tenant policy
    policy = await get_tenant_policy(state.tenant_id)

    # Check 1: Missing required inputs
    if state.current_intent in REQUIRED_FIELDS:
        required = REQUIRED_FIELDS[state.current_intent]
        missing = []

        for field in required:
            if field not in state.working_memory or not state.working_memory[field]:
                missing.append(field)

        if missing:
            hitl_request = create_missing_input_request(
                missing_fields=missing,
                context={"intent": state.current_intent.value},
            )

            await audit_logger.log_hitl_request(
                tenant_id=state.tenant_id,
                user_id=state.user_id,
                session_id=state.session_id,
                hitl_type=HITLType.MISSING_INPUT.value,
                request_id=hitl_request.id,
            )

            return {"hitl_pending": hitl_request}

    # Check 2: Internet search needed
    last_message = state.messages[-1].content if state.messages else ""
    needs_search, search_query = check_requires_internet_search(
        last_message,
        state.working_memory,
    )

    if needs_search and not policy.internet_search_enabled:
        # Internet search needed but not enabled
        hitl_request = create_internet_search_gate_request(search_query or last_message)

        await audit_logger.log_hitl_request(
            tenant_id=state.tenant_id,
            user_id=state.user_id,
            session_id=state.session_id,
            hitl_type=HITLType.INTERNET_SEARCH_GATE.value,
            request_id=hitl_request.id,
        )

        return {"hitl_pending": hitl_request}

    elif needs_search and policy.internet_search_requires_confirmation:
        # Search enabled but requires confirmation
        hitl_request = create_internet_search_gate_request(search_query or last_message)

        await audit_logger.log_hitl_request(
            tenant_id=state.tenant_id,
            user_id=state.user_id,
            session_id=state.session_id,
            hitl_type=HITLType.INTERNET_SEARCH_GATE.value,
            request_id=hitl_request.id,
        )

        return {"hitl_pending": hitl_request}

    return {}


def should_pause_for_hitl(state: AgentState) -> str:
    """Conditional edge: check if we should pause for HITL."""
    if state.hitl_pending:
        return "pause"
    return "continue"
```

---

### Task 3.7: Build Resume Handler

**packages/agent_core/src/agent_core/graph/nodes/resume_handler.py**
```python
"""Handler for resuming after HITL."""

from agent_core.state.models import AgentState
from agent_core.state.hitl import HITLResponse, HITLType
from agent_core.tools.tavily_search import search_internet
from agent_core.observability.audit import get_audit_logger
from common.logging import get_logger

logger = get_logger(__name__)


async def handle_resume(
    state: AgentState,
    response: HITLResponse,
) -> dict:
    """
    Process the HITL response and update state.
    """
    audit_logger = get_audit_logger()

    if not state.hitl_pending:
        logger.warning("No pending HITL request to resume")
        return {}

    request = state.hitl_pending

    # Log the response
    await audit_logger.log_hitl_response(
        tenant_id=state.tenant_id,
        user_id=state.user_id,
        session_id=state.session_id,
        request_id=request.id,
        response_summary=str(response.field_values or response.selected_option_id),
    )

    updates: dict = {
        "hitl_pending": None,  # Clear the pending request
    }

    # Process based on HITL type
    if request.hitl_type == HITLType.MISSING_INPUT:
        # Add provided values to working memory
        updates["working_memory"] = {
            **state.working_memory,
            **response.field_values,
        }

    elif request.hitl_type == HITLType.AMBIGUOUS_ENTITY:
        # Set the selected entity
        selected_id = response.selected_option_id
        entity_type = request.context.get("entity_type", "entity")

        if state.page_context:
            updates["page_context"] = state.page_context.model_copy(update={
                "entity_id": selected_id,
            })

        updates["working_memory"] = {
            **state.working_memory,
            f"selected_{entity_type}_id": selected_id,
        }

    elif request.hitl_type == HITLType.INTERNET_SEARCH_GATE:
        # Handle search permission
        selected = response.selected_option_id
        if selected == "allow":
            # User allowed search, perform it
            search_query = request.context.get("search_query", "")
            if search_query:
                search_result = await search_internet(search_query)
                updates["working_memory"] = {
                    **state.working_memory,
                    "internet_search_allowed": True,
                    "internet_search_results": [r.model_dump() for r in search_result.results],
                    "internet_search_answer": search_result.answer,
                }
        else:
            updates["working_memory"] = {
                **state.working_memory,
                "internet_search_allowed": False,
            }

    logger.info(
        "Processed HITL response",
        hitl_type=request.hitl_type.value,
        session_id=state.session_id,
    )

    return updates
```

---

### Task 3.8: Update Main Graph for HITL

**packages/agent_core/src/agent_core/graph/base_graph.py** (updated)
```python
"""Main LangGraph agent graph with HITL support."""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.base import BaseCheckpointSaver

from agent_core.state.models import AgentState, IntentType
from agent_core.graph.nodes.ingest_context import ingest_context
from agent_core.graph.nodes.route_intent import route_intent
from agent_core.graph.nodes.gather_context import gather_context
from agent_core.graph.nodes.hitl_gate import hitl_gate, should_pause_for_hitl
from agent_core.graph.nodes.draft_or_answer import draft_or_answer
from agent_core.graph.nodes.generate_content import generate_content
from agent_core.graph.nodes.finalize import finalize
from common.logging import get_logger

logger = get_logger(__name__)


def route_after_gather(state: AgentState) -> str:
    """Route based on intent after gathering context."""
    if state.current_intent in [IntentType.GENERATE, IntentType.EDIT]:
        return "generate_content"
    return "draft_or_answer"


def create_agent_graph() -> StateGraph:
    """
    Create the main agent graph with HITL support.

    Flow:
    ingest_context -> route_intent -> gather_context -> hitl_gate
                                                            |
                                                     [conditional]
                                                     /          \
                                                  pause      continue
                                                   |              |
                                                  END     [route by intent]
                                                          /            \
                                                   generate      draft_or_answer
                                                         \            /
                                                          finalize -> END
    """
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("ingest_context", ingest_context)
    graph.add_node("route_intent", route_intent)
    graph.add_node("gather_context", gather_context)
    graph.add_node("hitl_gate", hitl_gate)
    graph.add_node("draft_or_answer", draft_or_answer)
    graph.add_node("generate_content", generate_content)
    graph.add_node("finalize", finalize)

    # Add edges
    graph.set_entry_point("ingest_context")
    graph.add_edge("ingest_context", "route_intent")
    graph.add_edge("route_intent", "gather_context")
    graph.add_edge("gather_context", "hitl_gate")

    # HITL conditional
    graph.add_conditional_edges(
        "hitl_gate",
        should_pause_for_hitl,
        {
            "pause": END,  # Pause and wait for user input
            "continue": "route_by_intent",  # Continue processing
        },
    )

    # Add a routing node for intent
    def route_by_intent(state: AgentState) -> str:
        if state.current_intent in [IntentType.GENERATE, IntentType.EDIT]:
            return "generate_content"
        return "draft_or_answer"

    graph.add_node("route_by_intent", lambda x: x)  # Pass-through node
    graph.add_conditional_edges(
        "route_by_intent",
        route_by_intent,
        {
            "generate_content": "generate_content",
            "draft_or_answer": "draft_or_answer",
        },
    )

    graph.add_edge("generate_content", "finalize")
    graph.add_edge("draft_or_answer", "finalize")
    graph.add_edge("finalize", END)

    return graph


def compile_agent_graph(checkpointer: BaseCheckpointSaver | None = None):
    """Compile the graph with optional checkpointer."""
    graph = create_agent_graph()
    return graph.compile(checkpointer=checkpointer, interrupt_before=["hitl_gate"])
```

---

### Task 3.9: Add Resume API Endpoint

**apps/agent_api/src/agent_api/api/routes.py** (add to existing)
```python
# Add to imports
from agent_core.state.hitl import HITLResponse
from agent_core.graph.nodes.resume_handler import handle_resume

# Add new request model
class ResumeRequest(BaseModel):
    """Request to resume after HITL."""
    session_id: str
    tenant_id: str
    user_id: str
    hitl_response: HITLResponse


# Add endpoint
@router.post("/resume", response_model=ChatResponse)
async def resume_session(request: ResumeRequest) -> ChatResponse:
    """
    Resume a session after HITL interruption.

    Provide the HITL response and continue processing.
    """
    try:
        config = {
            "configurable": {
                "thread_id": request.session_id,
            }
        }

        # Get the current state from checkpoint
        state_snapshot = agent.get_state(config)

        if not state_snapshot or not state_snapshot.values:
            raise HTTPException(status_code=404, detail="Session not found")

        current_state = AgentState(**state_snapshot.values)

        if not current_state.hitl_pending:
            raise HTTPException(status_code=400, detail="No pending HITL request")

        # Process the resume
        updates = await handle_resume(current_state, request.hitl_response)

        # Update the state
        updated_state = current_state.model_copy(update=updates)

        # Continue the graph from where it paused
        result = await agent.ainvoke(updated_state.model_dump(), config=config)

        # Extract response
        messages = result.get("messages", [])
        last_message = messages[-1].content if messages else ""

        tool_results = [
            ToolResultResponse(
                tool_name=tr["tool_name"],
                input_summary=tr["input_summary"],
                output_summary=tr["output_summary"],
                latency_ms=tr["latency_ms"],
                success=tr["success"],
                citations=tr.get("citations", []),
            )
            for tr in result.get("tool_results", [])
        ]

        return ChatResponse(
            session_id=request.session_id,
            message=last_message,
            tool_results=tool_results,
            citations=[],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Resume error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
```

---

### Task 3.10: Update SSE Events for HITL

**apps/agent_api/src/agent_api/api/routes.py** (update stream endpoint)
```python
@router.post("/stream")
async def stream(request: ChatRequest) -> EventSourceResponse:
    """Streaming chat with HITL support."""

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            initial_state = build_initial_state(request)

            config = {
                "configurable": {
                    "thread_id": initial_state.session_id,
                }
            }

            yield json.dumps(SSEEvent(
                event_type=SSEEventType.STATUS,
                data={"status": "processing", "session_id": initial_state.session_id},
            ).model_dump())

            # Run the graph
            result = await agent.ainvoke(initial_state.model_dump(), config=config)

            # Check if paused for HITL
            if result.get("hitl_pending"):
                hitl_request = result["hitl_pending"]
                yield json.dumps(SSEEvent(
                    event_type=SSEEventType.HITL_REQUEST,
                    data={
                        "request_id": hitl_request.id,
                        "hitl_type": hitl_request.hitl_type,
                        "title": hitl_request.title,
                        "message": hitl_request.message,
                        "options": [o.model_dump() for o in hitl_request.options] if hitl_request.options else None,
                        "fields": [f.model_dump() for f in hitl_request.fields] if hitl_request.fields else None,
                    },
                ).model_dump())
                return

            # Continue with normal response...
            # (rest of the streaming logic)

        except Exception as e:
            logger.error("Stream error", error=str(e))
            yield json.dumps(SSEEvent(
                event_type=SSEEventType.ERROR,
                data={"error": str(e)},
            ).model_dump())

    return EventSourceResponse(event_generator())
```

---

## Azure Configuration Checklist

### 1. Create Policies Container (Optional)

If you want to persist tenant policies:

```bash
az cosmosdb sql container create \
  --account-name <your-cosmos-account> \
  --resource-group <your-rg> \
  --database-name invictus-copilot \
  --name policies \
  --partition-key-path /tenant_id \
  --throughput 400
```

### 2. Create Audit Logs Container (Optional)

For persistent audit logging:

```bash
az cosmosdb sql container create \
  --account-name <your-cosmos-account> \
  --resource-group <your-rg> \
  --database-name invictus-copilot \
  --name audit_logs \
  --partition-key-path /tenant_id \
  --throughput 400
```

### 3. Add Tavily API Key

Add to Key Vault:
```bash
az keyvault secret set \
  --vault-name <your-keyvault> \
  --name tavily-api-key \
  --value <your-tavily-key>
```

Update `.env`:
```env
TAVILY_API_KEY=your-tavily-key
```

---

## Testing Checklist

### Unit Tests

- [ ] `test_hitl_models.py` - HITL request/response validation
- [ ] `test_tool_policy.py` - Policy enforcement
- [ ] `test_audit_logger.py` - Audit event logging
- [ ] `test_hitl_gate.py` - HITL gate node logic
- [ ] `test_resume_handler.py` - Resume processing

### Integration Tests

- [ ] Trigger HITL for missing input and resume
- [ ] Trigger HITL for internet search gate
- [ ] Verify audit logs are created
- [ ] Test policy enforcement for disabled tools

### Manual Testing

```bash
# Trigger HITL for missing audience (generate request)
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Generate a report for this opportunity",
    "tenant_id": "test-tenant",
    "user_id": "test-user"
  }'

# Resume after HITL
curl -X POST http://localhost:8000/v1/copilot/resume \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "<session-id-from-above>",
    "tenant_id": "test-tenant",
    "user_id": "test-user",
    "hitl_response": {
      "request_id": "<request-id>",
      "field_values": {
        "audience": "investor"
      }
    }
  }'

# Test internet search gate
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is the current S&P 500 price?",
    "tenant_id": "test-tenant",
    "user_id": "test-user"
  }'
```

---

## Expected Deliverables

After completing Phase 3:

1. **HITL System**:
   - HITL models (request, response, options, fields)
   - HITL gate node in graph
   - Resume handler
   - `/resume` endpoint

2. **Tool Policy System**:
   - Tenant tool policy model
   - Policy store (with Cosmos persistence)
   - Policy enforcement in tools

3. **Tavily Integration**:
   - Internet search tool
   - Search gate with user confirmation
   - Results integration into context

4. **Audit Logging**:
   - Audit event model
   - Structured logging
   - Optional Cosmos persistence

5. **Working demo**:
   - Agent pauses for missing inputs
   - Agent pauses for internet search confirmation
   - User can resume with responses
   - Tool calls are audited

---

## Next Phase

Once Phase 3 is complete and tested, proceed to [Phase 4: MCP Ecosystem](phase-4-mcp-ecosystem.md).
