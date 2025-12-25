# Phase 1: MVP Copilot + Streaming + Cosmos Memory

## Objectives

- Build the core agent with LangGraph (AgentState, graph nodes, tool orchestration)
- Implement Cosmos DB checkpointer for session persistence
- Create FastAPI service with SSE streaming endpoints
- Integrate with existing RAG Gateway
- Build first MCP server (opportunities) with read-only tools
- Stream structured progress events to frontend

## Prerequisites

- Phase 0 completed (folder structure, dependencies, CI)
- Cosmos DB collections created (sessions, checkpoints, artifacts)
- Azure OpenAI endpoint configured
- RAG Gateway accessible
- Opportunities database accessible

---

## Implementation Tasks

### Task 1.1: Build Common Package

**packages/common/src/common/config.py**
```python
"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment
    environment: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"

    # Azure OpenAI
    azure_openai_endpoint: str = Field(..., description="Azure OpenAI endpoint URL")
    azure_openai_api_key: str = Field(..., description="Azure OpenAI API key")
    azure_openai_deployment_name: str = Field(default="gpt-4o")
    azure_openai_api_version: str = Field(default="2024-08-01-preview")

    # Cosmos DB
    cosmos_endpoint: str = Field(..., description="Cosmos DB endpoint URL")
    cosmos_key: str = Field(..., description="Cosmos DB primary key")
    cosmos_database_name: str = Field(default="invictus-copilot")
    cosmos_sessions_container: str = Field(default="sessions")
    cosmos_checkpoints_container: str = Field(default="checkpoints")
    cosmos_artifacts_container: str = Field(default="artifacts")

    # RAG Gateway
    rag_gateway_url: str = Field(..., description="RAG Gateway base URL")
    rag_gateway_api_key: str = Field(default="", description="RAG Gateway API key")

    # Tavily (optional)
    tavily_api_key: str = Field(default="", description="Tavily API key for internet search")

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
```

**packages/common/src/common/logging.py**
```python
"""Structured logging configuration using structlog."""

import logging
import sys
from typing import Any

import structlog


def setup_logging(log_level: str = "INFO", json_logs: bool = False) -> None:
    """Configure structured logging."""

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper()),
    )

    # Configure structlog
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.TimeStamper(fmt="iso"),
    ]

    if json_logs:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper())
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Get a logger instance."""
    return structlog.get_logger(name)
```

**packages/common/src/common/errors.py**
```python
"""Custom exception classes."""

from typing import Any


class InvictusError(Exception):
    """Base exception for Invictus AI platform."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConfigurationError(InvictusError):
    """Configuration-related errors."""
    pass


class AuthenticationError(InvictusError):
    """Authentication-related errors."""
    pass


class AuthorizationError(InvictusError):
    """Authorization-related errors."""
    pass


class ToolExecutionError(InvictusError):
    """Tool execution errors."""
    pass


class RAGGatewayError(InvictusError):
    """RAG Gateway communication errors."""
    pass


class MCPError(InvictusError):
    """MCP server communication errors."""
    pass


class SessionNotFoundError(InvictusError):
    """Session not found in storage."""
    pass


class CheckpointError(InvictusError):
    """Checkpoint save/load errors."""
    pass
```

---

### Task 1.2: Build Agent State Model

**packages/agent_core/src/agent_core/state/models.py**
```python
"""Agent state models for LangGraph."""

from datetime import datetime
from enum import Enum
from typing import Annotated, Any
from uuid import uuid4

from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field
from langgraph.graph.message import add_messages


class IntentType(str, Enum):
    """Types of user intents."""
    QA = "qa"
    GENERATE = "generate"
    EDIT = "edit"
    SUMMARIZE = "summarize"
    COMPARE = "compare"


class ToolPolicy(BaseModel):
    """Tool access policy for a session."""
    internet_search_enabled: bool = False
    rag_enabled: bool = True
    mcp_domains_enabled: list[str] = Field(default_factory=lambda: ["opportunities"])
    max_tool_calls: int = 10


class PageContext(BaseModel):
    """Context about the current page/screen."""
    module_id: str  # e.g., "deals", "crm", "risk"
    screen_name: str  # e.g., "opportunity_detail", "client_overview"
    entity_type: str | None = None  # e.g., "opportunity", "client"
    entity_id: str | None = None
    additional_context: dict[str, Any] = Field(default_factory=dict)


class DocumentSelection(BaseModel):
    """Selected documents for RAG."""
    doc_ids: list[str] = Field(default_factory=list)
    doc_sets: list[str] = Field(default_factory=list)  # e.g., "all_opportunity_docs"


class ToolResult(BaseModel):
    """Result from a tool execution."""
    tool_name: str
    input_summary: str
    output_summary: str
    latency_ms: float
    success: bool
    error: str | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Artifact(BaseModel):
    """Generated artifact (memo, report, etc.)."""
    artifact_id: str = Field(default_factory=lambda: str(uuid4()))
    artifact_type: str  # "memo", "report", "strategy_doc"
    title: str
    content: str  # Markdown content
    version: int = 1
    citations: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class HITLRequest(BaseModel):
    """Human-in-the-loop request."""
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    question: str
    options: list[str] | None = None
    required_fields: list[str] | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class AgentState(BaseModel):
    """Main agent state for LangGraph."""

    # Identity
    tenant_id: str
    user_id: str
    session_id: str = Field(default_factory=lambda: str(uuid4()))

    # Conversation
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)

    # Context
    page_context: PageContext | None = None
    selected_docs: DocumentSelection = Field(default_factory=DocumentSelection)

    # Policy
    tool_policy: ToolPolicy = Field(default_factory=ToolPolicy)

    # Working state
    current_intent: IntentType | None = None
    working_memory: dict[str, Any] = Field(default_factory=dict)
    tool_results: list[ToolResult] = Field(default_factory=list)

    # Artifacts
    artifacts: list[Artifact] = Field(default_factory=list)
    current_artifact_id: str | None = None

    # HITL
    hitl_pending: HITLRequest | None = None

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    tool_call_count: int = 0

    class Config:
        arbitrary_types_allowed = True
```

---

### Task 1.3: Build Cosmos DB Checkpointer

**packages/agent_core/src/agent_core/memory/cosmos_checkpointer.py**
```python
"""Cosmos DB checkpointer for LangGraph state persistence."""

from datetime import datetime
from typing import Any, Iterator, Optional, Sequence, Tuple
import json

from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langchain_core.runnables import RunnableConfig

from common.logging import get_logger

logger = get_logger(__name__)


class CosmosDBCheckpointer(BaseCheckpointSaver):
    """Checkpointer that persists LangGraph state to Cosmos DB."""

    def __init__(
        self,
        endpoint: str,
        key: str,
        database_name: str,
        container_name: str = "checkpoints",
    ):
        super().__init__()
        self.client = CosmosClient(endpoint, credential=key)
        self.database = self.client.get_database_client(database_name)
        self.container = self.database.get_container_client(container_name)

    def _make_id(self, thread_id: str, checkpoint_ns: str, checkpoint_id: str) -> str:
        """Create a unique document ID."""
        return f"{thread_id}:{checkpoint_ns}:{checkpoint_id}"

    def get_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        """Get a checkpoint tuple by config."""
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"].get("checkpoint_id")

        try:
            if checkpoint_id:
                # Get specific checkpoint
                doc_id = self._make_id(thread_id, checkpoint_ns, checkpoint_id)
                item = self.container.read_item(item=doc_id, partition_key=thread_id)
            else:
                # Get latest checkpoint
                query = """
                    SELECT TOP 1 * FROM c
                    WHERE c.thread_id = @thread_id
                    AND c.checkpoint_ns = @checkpoint_ns
                    ORDER BY c.created_at DESC
                """
                items = list(self.container.query_items(
                    query=query,
                    parameters=[
                        {"name": "@thread_id", "value": thread_id},
                        {"name": "@checkpoint_ns", "value": checkpoint_ns},
                    ],
                    partition_key=thread_id,
                ))
                if not items:
                    return None
                item = items[0]

            return CheckpointTuple(
                config=config,
                checkpoint=json.loads(item["checkpoint"]),
                metadata=json.loads(item.get("metadata", "{}")),
                parent_config=json.loads(item["parent_config"]) if item.get("parent_config") else None,
            )
        except CosmosResourceNotFoundError:
            return None
        except Exception as e:
            logger.error("Failed to get checkpoint", error=str(e), thread_id=thread_id)
            raise

    def list(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> Iterator[CheckpointTuple]:
        """List checkpoints for a thread."""
        if not config:
            return

        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")

        query = """
            SELECT * FROM c
            WHERE c.thread_id = @thread_id
            AND c.checkpoint_ns = @checkpoint_ns
            ORDER BY c.created_at DESC
        """
        params = [
            {"name": "@thread_id", "value": thread_id},
            {"name": "@checkpoint_ns", "value": checkpoint_ns},
        ]

        items = self.container.query_items(
            query=query,
            parameters=params,
            partition_key=thread_id,
            max_item_count=limit or 100,
        )

        for item in items:
            yield CheckpointTuple(
                config={
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": item["checkpoint_id"],
                    }
                },
                checkpoint=json.loads(item["checkpoint"]),
                metadata=json.loads(item.get("metadata", "{}")),
                parent_config=json.loads(item["parent_config"]) if item.get("parent_config") else None,
            )

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict[str, Any],
    ) -> RunnableConfig:
        """Save a checkpoint."""
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = checkpoint["id"]
        parent_config = config["configurable"].get("parent_config")

        doc_id = self._make_id(thread_id, checkpoint_ns, checkpoint_id)

        item = {
            "id": doc_id,
            "thread_id": thread_id,
            "checkpoint_ns": checkpoint_ns,
            "checkpoint_id": checkpoint_id,
            "checkpoint": json.dumps(checkpoint),
            "metadata": json.dumps(metadata),
            "parent_config": json.dumps(parent_config) if parent_config else None,
            "created_at": datetime.utcnow().isoformat(),
        }

        self.container.upsert_item(item)

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[Tuple[str, Any]],
        task_id: str,
    ) -> None:
        """Save intermediate writes (for pending tasks)."""
        # For MVP, we don't implement pending writes
        # This is needed for more advanced interrupt/resume scenarios
        pass
```

---

### Task 1.4: Build RAG Gateway Tool

**packages/agent_core/src/agent_core/tools/rag_gateway.py**
```python
"""RAG Gateway tool for document retrieval."""

from typing import Any

import httpx
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from common.config import get_settings
from common.errors import RAGGatewayError
from common.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class RAGQueryInput(BaseModel):
    """Input for RAG Gateway query."""
    query: str = Field(description="The search query")
    tenant_id: str = Field(description="Tenant ID for filtering")
    doc_ids: list[str] = Field(default_factory=list, description="Specific document IDs to search")
    doc_sets: list[str] = Field(default_factory=list, description="Document set names to search")
    top_k: int = Field(default=5, description="Number of results to return")


class RAGResult(BaseModel):
    """A single RAG result."""
    content: str
    doc_id: str
    doc_name: str
    chunk_id: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class RAGQueryOutput(BaseModel):
    """Output from RAG Gateway query."""
    results: list[RAGResult]
    query: str
    total_results: int


async def query_rag_gateway(
    query: str,
    tenant_id: str,
    doc_ids: list[str] | None = None,
    doc_sets: list[str] | None = None,
    top_k: int = 5,
) -> RAGQueryOutput:
    """Query the RAG Gateway for document retrieval."""

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            headers = {
                "Content-Type": "application/json",
            }
            if settings.rag_gateway_api_key:
                headers["Authorization"] = f"Bearer {settings.rag_gateway_api_key}"

            payload = {
                "query": query,
                "tenant_id": tenant_id,
                "top_k": top_k,
            }

            if doc_ids:
                payload["doc_ids"] = doc_ids
            if doc_sets:
                payload["doc_sets"] = doc_sets

            response = await client.post(
                f"{settings.rag_gateway_url}/v1/query",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()

            data = response.json()

            results = [
                RAGResult(
                    content=r.get("content", ""),
                    doc_id=r.get("doc_id", ""),
                    doc_name=r.get("doc_name", ""),
                    chunk_id=r.get("chunk_id", ""),
                    score=r.get("score", 0.0),
                    metadata=r.get("metadata", {}),
                )
                for r in data.get("results", [])
            ]

            logger.info(
                "RAG query completed",
                query=query[:50],
                result_count=len(results),
                tenant_id=tenant_id,
            )

            return RAGQueryOutput(
                results=results,
                query=query,
                total_results=len(results),
            )

        except httpx.HTTPStatusError as e:
            logger.error("RAG Gateway HTTP error", status=e.response.status_code)
            raise RAGGatewayError(f"RAG Gateway returned {e.response.status_code}")
        except Exception as e:
            logger.error("RAG Gateway error", error=str(e))
            raise RAGGatewayError(f"Failed to query RAG Gateway: {e}")


@tool
async def search_documents(
    query: str,
    tenant_id: str,
    doc_ids: list[str] | None = None,
    top_k: int = 5,
) -> str:
    """
    Search through selected documents to find relevant information.

    Use this tool when you need to find specific information from the user's documents.

    Args:
        query: The search query describing what information you're looking for
        tenant_id: The tenant ID (provided by context)
        doc_ids: Optional list of specific document IDs to search
        top_k: Number of results to return (default 5)

    Returns:
        Relevant document excerpts with citations
    """
    result = await query_rag_gateway(
        query=query,
        tenant_id=tenant_id,
        doc_ids=doc_ids,
        top_k=top_k,
    )

    if not result.results:
        return "No relevant documents found for the query."

    output_parts = [f"Found {len(result.results)} relevant excerpts:\n"]

    for i, r in enumerate(result.results, 1):
        output_parts.append(
            f"\n[{i}] From '{r.doc_name}' (relevance: {r.score:.2f}):\n{r.content}\n"
        )

    return "".join(output_parts)
```

---

### Task 1.5: Build MCP Client

**packages/agent_core/src/agent_core/tools/mcp_client.py**
```python
"""MCP client for calling domain MCP servers."""

from typing import Any

import httpx
from pydantic import BaseModel

from common.errors import MCPError
from common.logging import get_logger

logger = get_logger(__name__)


class MCPToolCall(BaseModel):
    """A call to an MCP tool."""
    server_url: str
    tool_name: str
    arguments: dict[str, Any]
    tenant_id: str


class MCPToolResult(BaseModel):
    """Result from an MCP tool call."""
    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None


async def call_mcp_tool(
    server_url: str,
    tool_name: str,
    arguments: dict[str, Any],
    timeout: float = 30.0,
) -> MCPToolResult:
    """Call a tool on an MCP server."""

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            # MCP uses JSON-RPC style calls
            payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments,
                },
                "id": 1,
            }

            response = await client.post(
                f"{server_url}/mcp",
                json=payload,
            )
            response.raise_for_status()

            result = response.json()

            if "error" in result:
                return MCPToolResult(
                    success=False,
                    error=result["error"].get("message", "Unknown error"),
                )

            return MCPToolResult(
                success=True,
                data=result.get("result", {}),
            )

        except httpx.HTTPStatusError as e:
            logger.error("MCP HTTP error", status=e.response.status_code, server=server_url)
            return MCPToolResult(success=False, error=f"HTTP {e.response.status_code}")
        except Exception as e:
            logger.error("MCP call error", error=str(e), server=server_url)
            return MCPToolResult(success=False, error=str(e))


class MCPClientRegistry:
    """Registry of MCP server endpoints."""

    def __init__(self):
        self._servers: dict[str, str] = {}

    def register(self, domain: str, url: str) -> None:
        """Register an MCP server."""
        self._servers[domain] = url

    def get_url(self, domain: str) -> str | None:
        """Get the URL for a domain's MCP server."""
        return self._servers.get(domain)

    def list_domains(self) -> list[str]:
        """List all registered domains."""
        return list(self._servers.keys())


# Global registry
mcp_registry = MCPClientRegistry()
```

---

### Task 1.6: Build LangGraph Nodes

**packages/agent_core/src/agent_core/graph/nodes/ingest_context.py**
```python
"""Ingest context node - validates and normalizes input."""

from agent_core.state.models import AgentState, PageContext, DocumentSelection, ToolPolicy
from common.logging import get_logger

logger = get_logger(__name__)


async def ingest_context(state: AgentState) -> dict:
    """
    Validate and normalize the incoming request context.

    This node:
    - Validates tenant_id and user_id
    - Normalizes page context
    - Loads tool policy for tenant
    """
    logger.info(
        "Ingesting context",
        tenant_id=state.tenant_id,
        session_id=state.session_id,
        module=state.page_context.module_id if state.page_context else None,
    )

    updates = {
        "working_memory": {
            **state.working_memory,
            "context_validated": True,
            "module": state.page_context.module_id if state.page_context else "unknown",
        }
    }

    # In a full implementation, we'd load tenant-specific policies here
    # For MVP, we use defaults

    return updates
```

**packages/agent_core/src/agent_core/graph/nodes/route_intent.py**
```python
"""Route intent node - classifies user intent."""

from langchain_core.messages import HumanMessage
from langchain_openai import AzureChatOpenAI

from agent_core.state.models import AgentState, IntentType
from common.config import get_settings
from common.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


INTENT_CLASSIFICATION_PROMPT = """Classify the user's intent into one of these categories:
- qa: Asking a question or seeking information
- generate: Requesting to create new content (report, memo, summary)
- edit: Requesting to modify existing content
- summarize: Requesting a summary of documents or data
- compare: Requesting comparison between items

User message: {message}

Respond with just the category name (qa, generate, edit, summarize, or compare)."""


async def route_intent(state: AgentState) -> dict:
    """
    Classify the user's intent based on their message.
    """
    # Get the last human message
    last_message = None
    for msg in reversed(state.messages):
        if isinstance(msg, HumanMessage):
            last_message = msg.content
            break

    if not last_message:
        return {"current_intent": IntentType.QA}

    # Use LLM to classify intent
    llm = AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        deployment_name=settings.azure_openai_deployment_name,
        temperature=0,
    )

    response = await llm.ainvoke(
        INTENT_CLASSIFICATION_PROMPT.format(message=last_message)
    )

    intent_str = response.content.strip().lower()

    intent_map = {
        "qa": IntentType.QA,
        "generate": IntentType.GENERATE,
        "edit": IntentType.EDIT,
        "summarize": IntentType.SUMMARIZE,
        "compare": IntentType.COMPARE,
    }

    intent = intent_map.get(intent_str, IntentType.QA)

    logger.info("Classified intent", intent=intent.value, message_preview=last_message[:50])

    return {"current_intent": intent}
```

**packages/agent_core/src/agent_core/graph/nodes/gather_context.py**
```python
"""Gather context node - retrieves relevant data from tools."""

from datetime import datetime

from agent_core.state.models import AgentState, ToolResult
from agent_core.tools.rag_gateway import query_rag_gateway
from agent_core.tools.mcp_client import call_mcp_tool, mcp_registry
from common.logging import get_logger

logger = get_logger(__name__)


async def gather_context(state: AgentState) -> dict:
    """
    Gather context by calling relevant tools.

    This node:
    - Calls MCP tools for entity data (if entity context provided)
    - Calls RAG Gateway (if documents selected)
    """
    tool_results = list(state.tool_results)

    # Get entity context from MCP if available
    if state.page_context and state.page_context.entity_id:
        entity_type = state.page_context.entity_type
        entity_id = state.page_context.entity_id

        # Check if domain is enabled
        domain = entity_type  # e.g., "opportunity" -> "opportunities"
        if domain in state.tool_policy.mcp_domains_enabled:
            server_url = mcp_registry.get_url(domain)
            if server_url:
                start = datetime.utcnow()

                result = await call_mcp_tool(
                    server_url=server_url,
                    tool_name=f"get_{entity_type}",
                    arguments={
                        f"{entity_type}_id": entity_id,
                        "tenant_id": state.tenant_id,
                    },
                )

                latency = (datetime.utcnow() - start).total_seconds() * 1000

                tool_results.append(ToolResult(
                    tool_name=f"mcp:{domain}:get_{entity_type}",
                    input_summary=f"Get {entity_type} {entity_id}",
                    output_summary=str(result.data)[:200] if result.success else result.error,
                    latency_ms=latency,
                    success=result.success,
                    error=result.error,
                ))

                if result.success and result.data:
                    # Store in working memory
                    return {
                        "tool_results": tool_results,
                        "working_memory": {
                            **state.working_memory,
                            f"{entity_type}_data": result.data,
                        },
                        "tool_call_count": state.tool_call_count + 1,
                    }

    # Query RAG if documents are selected
    if state.selected_docs.doc_ids or state.selected_docs.doc_sets:
        # Get the user's question from the last message
        last_message = state.messages[-1].content if state.messages else ""

        if last_message and state.tool_policy.rag_enabled:
            start = datetime.utcnow()

            try:
                rag_result = await query_rag_gateway(
                    query=last_message,
                    tenant_id=state.tenant_id,
                    doc_ids=state.selected_docs.doc_ids,
                    doc_sets=state.selected_docs.doc_sets,
                )

                latency = (datetime.utcnow() - start).total_seconds() * 1000

                tool_results.append(ToolResult(
                    tool_name="rag_gateway:query",
                    input_summary=f"Search: {last_message[:50]}",
                    output_summary=f"Found {len(rag_result.results)} results",
                    latency_ms=latency,
                    success=True,
                    citations=[
                        {"doc_id": r.doc_id, "doc_name": r.doc_name, "chunk_id": r.chunk_id}
                        for r in rag_result.results
                    ],
                ))

                return {
                    "tool_results": tool_results,
                    "working_memory": {
                        **state.working_memory,
                        "rag_results": [r.model_dump() for r in rag_result.results],
                    },
                    "tool_call_count": state.tool_call_count + 1,
                }
            except Exception as e:
                logger.error("RAG query failed", error=str(e))
                tool_results.append(ToolResult(
                    tool_name="rag_gateway:query",
                    input_summary=f"Search: {last_message[:50]}",
                    output_summary="",
                    latency_ms=0,
                    success=False,
                    error=str(e),
                ))

    return {"tool_results": tool_results}
```

**packages/agent_core/src/agent_core/graph/nodes/draft_or_answer.py**
```python
"""Draft or answer node - generates the response."""

from langchain_core.messages import AIMessage, HumanMessage
from langchain_openai import AzureChatOpenAI

from agent_core.state.models import AgentState, IntentType
from common.config import get_settings
from common.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


SYSTEM_PROMPT = """You are an AI assistant for Invictus AI, a wealth management platform.
You help users with:
- Answering questions about opportunities, clients, and investments
- Analyzing documents and data
- Generating reports and memos
- Summarizing information

Always be professional, accurate, and cite your sources when using document information.

{context}"""


def build_context(state: AgentState) -> str:
    """Build context string from working memory."""
    context_parts = []

    # Add entity data if available
    for key, value in state.working_memory.items():
        if key.endswith("_data") and isinstance(value, dict):
            entity_type = key.replace("_data", "")
            context_parts.append(f"\n{entity_type.title()} Information:\n{value}")

    # Add RAG results if available
    rag_results = state.working_memory.get("rag_results", [])
    if rag_results:
        context_parts.append("\nRelevant Document Excerpts:")
        for i, r in enumerate(rag_results[:5], 1):
            context_parts.append(f"\n[{i}] From '{r.get('doc_name', 'Unknown')}':")
            context_parts.append(r.get("content", "")[:500])

    return "\n".join(context_parts) if context_parts else "No additional context available."


async def draft_or_answer(state: AgentState) -> dict:
    """
    Generate a response based on the user's intent and gathered context.
    """
    llm = AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        deployment_name=settings.azure_openai_deployment_name,
        temperature=0.7,
    )

    context = build_context(state)
    system_prompt = SYSTEM_PROMPT.format(context=context)

    # Build messages for the LLM
    messages = [{"role": "system", "content": system_prompt}]

    for msg in state.messages:
        if isinstance(msg, HumanMessage):
            messages.append({"role": "user", "content": msg.content})
        elif isinstance(msg, AIMessage):
            messages.append({"role": "assistant", "content": msg.content})

    response = await llm.ainvoke(messages)

    logger.info(
        "Generated response",
        intent=state.current_intent.value if state.current_intent else "unknown",
        response_length=len(response.content),
    )

    return {
        "messages": [AIMessage(content=response.content)],
    }
```

**packages/agent_core/src/agent_core/graph/nodes/finalize.py**
```python
"""Finalize node - persists state and prepares final output."""

from datetime import datetime

from agent_core.state.models import AgentState
from common.logging import get_logger

logger = get_logger(__name__)


async def finalize(state: AgentState) -> dict:
    """
    Finalize the response and prepare for checkpointing.
    """
    logger.info(
        "Finalizing response",
        session_id=state.session_id,
        tool_calls=state.tool_call_count,
        artifacts=len(state.artifacts),
    )

    return {
        "updated_at": datetime.utcnow(),
    }
```

---

### Task 1.7: Build the Main Graph

**packages/agent_core/src/agent_core/graph/base_graph.py**
```python
"""Main LangGraph agent graph."""

from langgraph.graph import StateGraph, END

from agent_core.state.models import AgentState
from agent_core.graph.nodes.ingest_context import ingest_context
from agent_core.graph.nodes.route_intent import route_intent
from agent_core.graph.nodes.gather_context import gather_context
from agent_core.graph.nodes.draft_or_answer import draft_or_answer
from agent_core.graph.nodes.finalize import finalize
from common.logging import get_logger

logger = get_logger(__name__)


def create_agent_graph() -> StateGraph:
    """
    Create the main agent graph.

    Flow:
    ingest_context -> route_intent -> gather_context -> draft_or_answer -> finalize -> END
    """

    # Create the graph with our state type
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("ingest_context", ingest_context)
    graph.add_node("route_intent", route_intent)
    graph.add_node("gather_context", gather_context)
    graph.add_node("draft_or_answer", draft_or_answer)
    graph.add_node("finalize", finalize)

    # Add edges (simple linear flow for MVP)
    graph.set_entry_point("ingest_context")
    graph.add_edge("ingest_context", "route_intent")
    graph.add_edge("route_intent", "gather_context")
    graph.add_edge("gather_context", "draft_or_answer")
    graph.add_edge("draft_or_answer", "finalize")
    graph.add_edge("finalize", END)

    return graph


def compile_agent_graph(checkpointer=None):
    """Compile the graph with optional checkpointer."""
    graph = create_agent_graph()
    return graph.compile(checkpointer=checkpointer)
```

---

### Task 1.8: Build FastAPI Application

**apps/agent_api/src/agent_api/api/schemas.py**
```python
"""API request/response schemas."""

from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class PageContextRequest(BaseModel):
    """Page context in request."""
    module_id: str
    screen_name: str
    entity_type: str | None = None
    entity_id: str | None = None
    additional_context: dict[str, Any] = Field(default_factory=dict)


class DocumentSelectionRequest(BaseModel):
    """Document selection in request."""
    doc_ids: list[str] = Field(default_factory=list)
    doc_sets: list[str] = Field(default_factory=list)


class ChatRequest(BaseModel):
    """Chat request payload."""
    message: str
    tenant_id: str
    user_id: str
    session_id: str | None = None
    page_context: PageContextRequest | None = None
    selected_docs: DocumentSelectionRequest | None = None
    internet_search_enabled: bool = False


class ToolResultResponse(BaseModel):
    """Tool result in response."""
    tool_name: str
    input_summary: str
    output_summary: str
    latency_ms: float
    success: bool
    citations: list[dict[str, Any]] = Field(default_factory=list)


class ChatResponse(BaseModel):
    """Chat response payload."""
    session_id: str
    message: str
    tool_results: list[ToolResultResponse] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)


class SessionResponse(BaseModel):
    """Session info response."""
    session_id: str
    tenant_id: str
    user_id: str
    created_at: datetime
    message_count: int


# SSE Event Types
class SSEEventType(str, Enum):
    STATUS = "status"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_RESULT = "tool_call_result"
    ASSISTANT_DELTA = "assistant_delta"
    ARTIFACT_UPDATE = "artifact_update"
    HITL_REQUEST = "hitl_request"
    FINAL = "final"
    ERROR = "error"


class SSEEvent(BaseModel):
    """Server-Sent Event payload."""
    event_type: SSEEventType
    data: dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
```

**apps/agent_api/src/agent_api/api/routes.py**
```python
"""API routes for the Copilot service."""

import asyncio
import json
from datetime import datetime
from typing import AsyncGenerator
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from langchain_core.messages import HumanMessage
from sse_starlette.sse import EventSourceResponse

from agent_api.api.schemas import (
    ChatRequest,
    ChatResponse,
    SessionResponse,
    SSEEvent,
    SSEEventType,
    ToolResultResponse,
)
from agent_core.graph.base_graph import compile_agent_graph
from agent_core.memory.cosmos_checkpointer import CosmosDBCheckpointer
from agent_core.state.models import (
    AgentState,
    PageContext,
    DocumentSelection,
    ToolPolicy,
)
from common.config import get_settings
from common.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter(prefix="/v1/copilot", tags=["copilot"])

# Initialize checkpointer
checkpointer = CosmosDBCheckpointer(
    endpoint=settings.cosmos_endpoint,
    key=settings.cosmos_key,
    database_name=settings.cosmos_database_name,
    container_name=settings.cosmos_checkpoints_container,
)

# Compile the graph with checkpointer
agent = compile_agent_graph(checkpointer=checkpointer)


def build_initial_state(request: ChatRequest) -> AgentState:
    """Build initial agent state from request."""
    page_context = None
    if request.page_context:
        page_context = PageContext(
            module_id=request.page_context.module_id,
            screen_name=request.page_context.screen_name,
            entity_type=request.page_context.entity_type,
            entity_id=request.page_context.entity_id,
            additional_context=request.page_context.additional_context,
        )

    selected_docs = DocumentSelection()
    if request.selected_docs:
        selected_docs = DocumentSelection(
            doc_ids=request.selected_docs.doc_ids,
            doc_sets=request.selected_docs.doc_sets,
        )

    return AgentState(
        tenant_id=request.tenant_id,
        user_id=request.user_id,
        session_id=request.session_id or str(uuid4()),
        messages=[HumanMessage(content=request.message)],
        page_context=page_context,
        selected_docs=selected_docs,
        tool_policy=ToolPolicy(
            internet_search_enabled=request.internet_search_enabled,
        ),
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Non-streaming chat endpoint.

    Processes the request and returns the complete response.
    """
    try:
        initial_state = build_initial_state(request)

        config = {
            "configurable": {
                "thread_id": initial_state.session_id,
            }
        }

        # Run the graph
        result = await agent.ainvoke(initial_state.model_dump(), config=config)

        # Extract the response
        messages = result.get("messages", [])
        last_message = messages[-1].content if messages else "I couldn't generate a response."

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

        # Collect citations
        citations = []
        for tr in tool_results:
            citations.extend(tr.citations)

        return ChatResponse(
            session_id=initial_state.session_id,
            message=last_message,
            tool_results=tool_results,
            citations=citations,
        )

    except Exception as e:
        logger.error("Chat error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stream")
async def stream(request: ChatRequest) -> EventSourceResponse:
    """
    Streaming chat endpoint using SSE.

    Emits events as the agent processes the request.
    """

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            initial_state = build_initial_state(request)

            config = {
                "configurable": {
                    "thread_id": initial_state.session_id,
                }
            }

            # Emit status event
            yield json.dumps(SSEEvent(
                event_type=SSEEventType.STATUS,
                data={"status": "processing", "session_id": initial_state.session_id},
            ).model_dump())

            # For MVP, we run the graph and stream the result
            # In a full implementation, we'd use graph streaming

            yield json.dumps(SSEEvent(
                event_type=SSEEventType.STATUS,
                data={"status": "gathering_context"},
            ).model_dump())

            result = await agent.ainvoke(initial_state.model_dump(), config=config)

            # Emit tool results
            for tr in result.get("tool_results", []):
                yield json.dumps(SSEEvent(
                    event_type=SSEEventType.TOOL_CALL_RESULT,
                    data={
                        "tool_name": tr["tool_name"],
                        "success": tr["success"],
                        "latency_ms": tr["latency_ms"],
                    },
                ).model_dump())

            # Emit the response
            messages = result.get("messages", [])
            last_message = messages[-1].content if messages else ""

            # Stream the response in chunks
            yield json.dumps(SSEEvent(
                event_type=SSEEventType.STATUS,
                data={"status": "generating_response"},
            ).model_dump())

            # Emit response in chunks for streaming effect
            chunk_size = 50
            for i in range(0, len(last_message), chunk_size):
                chunk = last_message[i:i + chunk_size]
                yield json.dumps(SSEEvent(
                    event_type=SSEEventType.ASSISTANT_DELTA,
                    data={"content": chunk},
                ).model_dump())
                await asyncio.sleep(0.02)  # Small delay for streaming effect

            # Emit final event
            yield json.dumps(SSEEvent(
                event_type=SSEEventType.FINAL,
                data={
                    "session_id": initial_state.session_id,
                    "message": last_message,
                    "tool_call_count": result.get("tool_call_count", 0),
                },
            ).model_dump())

        except Exception as e:
            logger.error("Stream error", error=str(e))
            yield json.dumps(SSEEvent(
                event_type=SSEEventType.ERROR,
                data={"error": str(e)},
            ).model_dump())

    return EventSourceResponse(event_generator())


@router.post("/sessions", response_model=SessionResponse)
async def create_session(tenant_id: str, user_id: str) -> SessionResponse:
    """Create a new session."""
    session_id = str(uuid4())

    return SessionResponse(
        session_id=session_id,
        tenant_id=tenant_id,
        user_id=user_id,
        created_at=datetime.utcnow(),
        message_count=0,
    )


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str) -> SessionResponse:
    """Get session information."""
    # For MVP, return mock data
    # In full implementation, retrieve from Cosmos DB
    return SessionResponse(
        session_id=session_id,
        tenant_id="unknown",
        user_id="unknown",
        created_at=datetime.utcnow(),
        message_count=0,
    )
```

**apps/agent_api/src/agent_api/main.py**
```python
"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from agent_api.api.routes import router
from common.config import get_settings
from common.logging import setup_logging, get_logger

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    setup_logging(
        log_level=settings.log_level,
        json_logs=settings.is_production,
    )
    logger = get_logger(__name__)
    logger.info("Starting Invictus AI Copilot API", environment=settings.environment)

    yield

    # Shutdown
    logger.info("Shutting down Invictus AI Copilot API")


app = FastAPI(
    title="Invictus AI Copilot API",
    description="AI Copilot Agent for Invictus AI wealth management platform",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(router)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "version": "0.1.0"}


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": "Invictus AI Copilot API",
        "version": "0.1.0",
        "docs": "/docs",
    }
```

---

### Task 1.9: Build First MCP Server (Opportunities)

**apps/mcp_servers/opportunities/src/mcp_opportunities/server.py**
```python
"""MCP server for opportunities domain."""

from fastmcp import FastMCP

from mcp_opportunities.tools import (
    get_opportunity,
    get_opportunity_kpis,
    list_opportunity_documents,
)

# Create the MCP server
mcp = FastMCP("Opportunities MCP Server")

# Register tools
mcp.tool(get_opportunity)
mcp.tool(get_opportunity_kpis)
mcp.tool(list_opportunity_documents)


if __name__ == "__main__":
    mcp.run()
```

**apps/mcp_servers/opportunities/src/mcp_opportunities/tools.py**
```python
"""Tools for the opportunities MCP server."""

from typing import Any

from mcp_opportunities.db import get_db_connection
from mcp_opportunities.schemas import (
    Opportunity,
    OpportunityKPIs,
    OpportunityDocument,
)
from mcp_common.auth import validate_tenant_access


async def get_opportunity(
    opportunity_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    """
    Get detailed information about an opportunity.

    Args:
        opportunity_id: The unique identifier of the opportunity
        tenant_id: The tenant ID for access control

    Returns:
        Opportunity details including name, status, value, and key dates
    """
    validate_tenant_access(tenant_id)

    async with get_db_connection() as conn:
        # Example query - adjust based on your actual schema
        query = """
            SELECT
                id, name, status, deal_value, currency,
                target_close_date, created_at, updated_at,
                description, deal_type, stage
            FROM opportunities
            WHERE id = ? AND tenant_id = ?
        """

        row = await conn.fetchone(query, (opportunity_id, tenant_id))

        if not row:
            return {"error": "Opportunity not found"}

        return Opportunity(
            id=row["id"],
            name=row["name"],
            status=row["status"],
            deal_value=row["deal_value"],
            currency=row["currency"],
            target_close_date=row["target_close_date"],
            description=row["description"],
            deal_type=row["deal_type"],
            stage=row["stage"],
        ).model_dump()


async def get_opportunity_kpis(
    opportunity_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    """
    Get key performance indicators for an opportunity.

    Args:
        opportunity_id: The unique identifier of the opportunity
        tenant_id: The tenant ID for access control

    Returns:
        KPIs including IRR, multiple, fees, and risk metrics
    """
    validate_tenant_access(tenant_id)

    async with get_db_connection() as conn:
        query = """
            SELECT
                opportunity_id, target_irr, target_multiple,
                management_fee, performance_fee,
                investment_period_years, total_fund_size,
                risk_rating, vintage_year
            FROM opportunity_kpis
            WHERE opportunity_id = ? AND tenant_id = ?
        """

        row = await conn.fetchone(query, (opportunity_id, tenant_id))

        if not row:
            return {"error": "KPIs not found for this opportunity"}

        return OpportunityKPIs(
            opportunity_id=row["opportunity_id"],
            target_irr=row["target_irr"],
            target_multiple=row["target_multiple"],
            management_fee=row["management_fee"],
            performance_fee=row["performance_fee"],
            investment_period_years=row["investment_period_years"],
            total_fund_size=row["total_fund_size"],
            risk_rating=row["risk_rating"],
            vintage_year=row["vintage_year"],
        ).model_dump()


async def list_opportunity_documents(
    opportunity_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    """
    List all documents associated with an opportunity.

    Args:
        opportunity_id: The unique identifier of the opportunity
        tenant_id: The tenant ID for access control

    Returns:
        List of documents with their types and metadata
    """
    validate_tenant_access(tenant_id)

    async with get_db_connection() as conn:
        query = """
            SELECT
                id, name, document_type, file_size,
                uploaded_at, uploaded_by
            FROM opportunity_documents
            WHERE opportunity_id = ? AND tenant_id = ?
            ORDER BY uploaded_at DESC
        """

        rows = await conn.fetchall(query, (opportunity_id, tenant_id))

        documents = [
            OpportunityDocument(
                id=row["id"],
                name=row["name"],
                document_type=row["document_type"],
                file_size=row["file_size"],
                uploaded_at=row["uploaded_at"],
            ).model_dump()
            for row in rows
        ]

        return {"documents": documents, "count": len(documents)}
```

**apps/mcp_servers/opportunities/src/mcp_opportunities/schemas.py**
```python
"""Schemas for opportunities domain."""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class Opportunity(BaseModel):
    """Opportunity data model."""
    id: str
    name: str
    status: str
    deal_value: Decimal
    currency: str
    target_close_date: Optional[datetime] = None
    description: Optional[str] = None
    deal_type: Optional[str] = None
    stage: Optional[str] = None


class OpportunityKPIs(BaseModel):
    """Opportunity KPIs data model."""
    opportunity_id: str
    target_irr: Optional[Decimal] = None
    target_multiple: Optional[Decimal] = None
    management_fee: Optional[Decimal] = None
    performance_fee: Optional[Decimal] = None
    investment_period_years: Optional[int] = None
    total_fund_size: Optional[Decimal] = None
    risk_rating: Optional[str] = None
    vintage_year: Optional[int] = None


class OpportunityDocument(BaseModel):
    """Opportunity document data model."""
    id: str
    name: str
    document_type: str
    file_size: int
    uploaded_at: datetime
```

**apps/mcp_servers/opportunities/src/mcp_opportunities/db.py**
```python
"""Database connection for opportunities MCP server."""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

# This is a placeholder - implement based on your actual DB
# Example using aioodbc for SQL Server:

class DatabaseConnection:
    """Async database connection wrapper."""

    def __init__(self, connection):
        self._conn = connection

    async def fetchone(self, query: str, params: tuple = None):
        """Fetch a single row."""
        cursor = await self._conn.cursor()
        await cursor.execute(query, params or ())
        row = await cursor.fetchone()
        if row:
            columns = [column[0] for column in cursor.description]
            return dict(zip(columns, row))
        return None

    async def fetchall(self, query: str, params: tuple = None):
        """Fetch all rows."""
        cursor = await self._conn.cursor()
        await cursor.execute(query, params or ())
        rows = await cursor.fetchall()
        columns = [column[0] for column in cursor.description]
        return [dict(zip(columns, row)) for row in rows]


@asynccontextmanager
async def get_db_connection() -> AsyncGenerator[DatabaseConnection, None]:
    """
    Get a database connection.

    Configure connection based on environment variables.
    """
    # Placeholder implementation
    # Replace with actual DB connection logic

    connection_string = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={os.getenv('OPPORTUNITIES_DB_HOST')};"
        f"DATABASE={os.getenv('OPPORTUNITIES_DB_NAME')};"
        f"UID={os.getenv('OPPORTUNITIES_DB_USER')};"
        f"PWD={os.getenv('OPPORTUNITIES_DB_PASSWORD')}"
    )

    # For MVP, return a mock connection
    # In production, use actual DB connection
    class MockConnection:
        async def cursor(self):
            return self
        async def execute(self, query, params):
            pass
        async def fetchone(self):
            return None
        async def fetchall(self):
            return []
        @property
        def description(self):
            return []

    yield DatabaseConnection(MockConnection())
```

---

### Task 1.10: Build MCP Common Package

**packages/mcp_common/src/mcp_common/auth.py**
```python
"""Authentication utilities for MCP servers."""

from common.errors import AuthorizationError


def validate_tenant_access(tenant_id: str) -> None:
    """
    Validate that the tenant has access.

    For MVP, this is a simple validation.
    In production, verify against tenant registry.
    """
    if not tenant_id:
        raise AuthorizationError("tenant_id is required")

    # Add more validation as needed
    # e.g., check against allowed tenant list


def validate_user_access(user_id: str, tenant_id: str, resource_type: str) -> None:
    """
    Validate that the user has access to a resource type.

    For MVP, this is a placeholder.
    In production, check user permissions.
    """
    if not user_id:
        raise AuthorizationError("user_id is required")
```

**packages/mcp_common/src/mcp_common/telemetry.py**
```python
"""Telemetry utilities for MCP servers."""

import time
from contextlib import contextmanager
from typing import Any, Generator

from common.logging import get_logger

logger = get_logger(__name__)


@contextmanager
def track_tool_call(
    tool_name: str,
    tenant_id: str,
    user_id: str | None = None,
) -> Generator[dict[str, Any], None, None]:
    """
    Context manager to track tool call metrics.

    Usage:
        with track_tool_call("get_opportunity", tenant_id) as metrics:
            result = await do_work()
            metrics["result_count"] = len(result)
    """
    metrics: dict[str, Any] = {
        "tool_name": tool_name,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "start_time": time.time(),
    }

    try:
        yield metrics
        metrics["success"] = True
    except Exception as e:
        metrics["success"] = False
        metrics["error"] = str(e)
        raise
    finally:
        metrics["duration_ms"] = (time.time() - metrics["start_time"]) * 1000

        logger.info(
            "Tool call completed",
            tool_name=tool_name,
            tenant_id=tenant_id,
            duration_ms=metrics["duration_ms"],
            success=metrics.get("success", False),
        )
```

---

## Azure Configuration Checklist

### 1. Verify Cosmos DB Collections

Ensure the following containers exist with correct partition keys:

| Container | Partition Key | Purpose |
|-----------|--------------|---------|
| sessions | /tenant_id | Session metadata |
| checkpoints | /thread_id | LangGraph checkpoints |
| artifacts | /tenant_id | Generated artifacts |

### 2. Configure Azure OpenAI

- [ ] Note the endpoint URL (e.g., `https://your-resource.openai.azure.com/`)
- [ ] Note the API key
- [ ] Create a deployment for `gpt-4o` or your preferred model
- [ ] Note the deployment name and API version

### 3. Configure RAG Gateway Access

- [ ] Ensure the RAG Gateway is accessible from where the agent API will run
- [ ] Note the base URL and API key (if required)

### 4. Configure Opportunities Database Access

- [ ] Create a read-only database user
- [ ] Note connection details (host, database, user, password)
- [ ] Test connectivity from your development environment

### 5. Update .env File

```env
# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o
AZURE_OPENAI_API_VERSION=2024-08-01-preview

# Cosmos DB
COSMOS_ENDPOINT=https://your-cosmos.documents.azure.com:443/
COSMOS_KEY=your-cosmos-key
COSMOS_DATABASE_NAME=invictus-copilot

# RAG Gateway
RAG_GATEWAY_URL=https://your-rag-gateway.azurewebsites.net
RAG_GATEWAY_API_KEY=your-rag-key

# Opportunities DB
OPPORTUNITIES_DB_HOST=your-sql-server.database.windows.net
OPPORTUNITIES_DB_NAME=opportunities
OPPORTUNITIES_DB_USER=readonly_user
OPPORTUNITIES_DB_PASSWORD=your-password
```

---

## Testing Checklist

### Unit Tests

- [ ] `test_agent_state.py` - State model validation
- [ ] `test_cosmos_checkpointer.py` - Checkpointer save/load
- [ ] `test_rag_gateway.py` - RAG tool (with mocks)
- [ ] `test_graph_nodes.py` - Individual node functions

### Integration Tests

- [ ] Test `/health` endpoint returns 200
- [ ] Test `/v1/copilot/chat` with simple Q&A
- [ ] Test `/v1/copilot/stream` SSE events
- [ ] Test session creation and retrieval

### Manual Testing

```bash
# Start the API
uvicorn apps.agent_api.src.agent_api.main:app --reload

# Test health
curl http://localhost:8000/health

# Test chat
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is this opportunity about?",
    "tenant_id": "test-tenant",
    "user_id": "test-user",
    "page_context": {
      "module_id": "deals",
      "screen_name": "opportunity_detail",
      "entity_type": "opportunity",
      "entity_id": "opp-123"
    }
  }'

# Test streaming (use curl with SSE support)
curl -N http://localhost:8000/v1/copilot/stream \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Summarize the key risks",
    "tenant_id": "test-tenant",
    "user_id": "test-user"
  }'
```

---

## Expected Deliverables

After completing Phase 1:

1. **packages/agent_core/** - Fully functional agent with:
   - AgentState model with all required fields
   - LangGraph with 5 nodes (ingest → route → gather → draft → finalize)
   - Cosmos DB checkpointer for session persistence
   - RAG Gateway tool wrapper
   - MCP client for calling domain servers

2. **packages/common/** - Configuration, logging, and error handling

3. **apps/agent_api/** - FastAPI service with:
   - `/v1/copilot/chat` - Non-streaming endpoint
   - `/v1/copilot/stream` - SSE streaming endpoint
   - `/v1/sessions` - Session management
   - `/health` - Health check

4. **apps/mcp_servers/opportunities/** - First MCP server with:
   - `get_opportunity` tool
   - `get_opportunity_kpis` tool
   - `list_opportunity_documents` tool

5. **Working demo**: Deals module can ask questions and receive streamed responses with tool activity visible

---

## Next Phase

Once Phase 1 is complete and tested, proceed to [Phase 2: Content Generation](phase-2-content-generation.md).
