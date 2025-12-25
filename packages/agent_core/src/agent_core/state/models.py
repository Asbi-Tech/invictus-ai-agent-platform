"""Agent state models for LangGraph."""

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Callable, Awaitable
from uuid import uuid4

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


class IntentType(str, Enum):
    """Types of user intents the agent can handle."""

    QA = "qa"  # Question answering
    GENERATE = "generate"  # Content generation (reports, memos)
    EDIT = "edit"  # Edit existing content
    SUMMARIZE = "summarize"  # Summarize documents/data
    COMPARE = "compare"  # Compare items/documents
    # Agent-specific intents
    CREATE_ARTIFACT = "create_artifact"  # Create new artifact
    EDIT_ARTIFACT = "edit_artifact"  # Edit existing artifact


class RequestType(str, Enum):
    """Types of requests."""

    ASK = "ask"
    AGENT = "agent"


class AgentCase(str, Enum):
    """Agent mode action types."""

    EDIT = "edit"
    CREATE = "create"


class EditOperation(str, Enum):
    """Types of edit operations for artifacts."""

    ADD = "add"
    REMOVE = "remove"
    MODIFY = "modify"


class ToolPolicy(BaseModel):
    """Tool access policy for a session."""

    web_search_enabled: bool = False
    rag_enabled: bool = True
    enabled_mcps: list[str] = Field(
        default_factory=lambda: ["deals"]
    )
    max_tool_calls: int = 10

    # Backward compatibility properties
    @property
    def internet_search_enabled(self) -> bool:
        """Alias for web_search_enabled."""
        return self.web_search_enabled

    @property
    def mcp_domains_enabled(self) -> list[str]:
        """Alias for enabled_mcps."""
        return self.enabled_mcps


class PageContext(BaseModel):
    """Context about the current page/screen in the UI."""

    module_id: str = "deals"  # e.g., "deals", "crm", "risk", "client_portal"
    screen_name: str  # e.g., "opportunity_detail", "client_overview"
    # New opportunity-specific fields
    opportunity_id: str | None = None
    opportunity_name: str | None = None
    screen_highlights: dict[str, Any] = Field(default_factory=dict)
    # Backward compatibility fields
    entity_type: str | None = None  # e.g., "opportunity", "client"
    entity_id: str | None = None
    additional_context: dict[str, Any] = Field(default_factory=dict)


class StorageConfig(BaseModel):
    """Azure Blob Storage configuration for document access."""

    account_url: str
    filesystem: str = "documents"
    base_prefix: str


class DocumentSelection(BaseModel):
    """Selected documents for RAG operations."""

    doc_ids: list[str] = Field(default_factory=list)
    doc_sets: list[str] = Field(default_factory=list)  # e.g., "all_opportunity_docs"
    storage: StorageConfig | None = None  # For MVP testing without MCP


class FieldDefinition(BaseModel):
    """Field definition for RAG extraction."""

    name: str
    description: str
    instructions: str
    type: str = "string"  # string, number, object, array
    options: list[str] | None = None  # For constrained values


class ToolResult(BaseModel):
    """Result from a tool execution."""

    tool_name: str
    input_summary: str
    output_summary: str
    latency_ms: float
    success: bool
    error: str | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    raw_output: dict[str, Any] | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Artifact(BaseModel):
    """Generated artifact (memo, report, etc.)."""

    artifact_id: str = Field(default_factory=lambda: str(uuid4()))
    artifact_type: str  # "memo", "report", "strategy_doc", "summary"
    title: str
    content: str  # Markdown content
    version: int = 1
    citations: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class HITLRequest(BaseModel):
    """Human-in-the-loop request for user input."""

    request_id: str = Field(default_factory=lambda: str(uuid4()))
    question: str
    options: list[str] | None = None  # For multiple choice
    required_fields: list[str] | None = None  # For form input
    context: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = 300  # 5 minutes default


class EditInstruction(BaseModel):
    """Edit instruction for artifact modification (diff-based)."""

    operation: EditOperation
    section_id: str | None = None
    section_title: str | None = None
    position: str | None = None  # before, after, replace
    content: str | None = None
    reasoning: str = ""


# Type alias for SSE callback
SSECallbackType = Callable[[str, str | dict, str | None], Awaitable[None]]


class AgentState(BaseModel):
    """
    Main agent state for LangGraph.

    This state is persisted to Cosmos DB via the checkpointer and flows
    through all graph nodes. Extended to support ask/agent modes.
    """

    # Identity
    tenant_id: str
    user_id: str
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    module_id: str = "deals"

    # Request type (ask vs agent)
    request_type: RequestType = RequestType.ASK
    agent_case: AgentCase | None = None

    # Conversation history (uses LangGraph's add_messages reducer)
    messages: Annotated[list[BaseMessage], add_messages] = Field(default_factory=list)

    # Additional context from user
    additional_prompt: str | None = None

    # Context from the UI
    page_context: PageContext | None = None
    document_ids: list[str] = Field(default_factory=list)
    selected_docs: DocumentSelection = Field(default_factory=DocumentSelection)

    # Current artifact for edit mode (input)
    current_artifact: Artifact | None = None

    # Edit instructions generated by agent edit mode
    edit_instructions: list[EditInstruction] = Field(default_factory=list)

    # Policy controlling tool access
    tool_policy: ToolPolicy = Field(default_factory=ToolPolicy)

    # Working state (cleared between requests)
    current_intent: IntentType | None = None
    working_memory: dict[str, Any] = Field(default_factory=dict)
    tool_results: list[ToolResult] = Field(default_factory=list)

    # Artifacts generated during session
    artifacts: list[Artifact] = Field(default_factory=list)
    current_artifact_id: str | None = None

    # Human-in-the-loop state
    hitl_pending: HITLRequest | None = None

    # SSE callback for streaming events (excluded from serialization)
    sse_callback: SSECallbackType | None = Field(default=None, exclude=True)

    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    tool_call_count: int = 0
    error_count: int = 0

    model_config = {"arbitrary_types_allowed": True}

    def get_last_human_message(self) -> str | None:
        """Get the content of the last human message."""
        from langchain_core.messages import HumanMessage

        for msg in reversed(self.messages):
            if isinstance(msg, HumanMessage):
                return str(msg.content)
        return None

    def get_last_ai_message(self) -> str | None:
        """Get the content of the last AI message."""
        from langchain_core.messages import AIMessage

        for msg in reversed(self.messages):
            if isinstance(msg, AIMessage):
                return str(msg.content)
        return None

    def add_tool_result(self, result: ToolResult) -> None:
        """Add a tool result to the state."""
        self.tool_results.append(result)
        self.tool_call_count += 1

    def get_rag_context(self) -> str:
        """Get formatted RAG context from tool results for LLM."""
        rag_results = self.working_memory.get("rag_results", {})
        if not rag_results:
            return ""

        context_parts = []
        for field_name, field_value in rag_results.items():
            if field_value is not None:
                context_parts.append(f"**{field_name}**: {field_value}")

        return "\n".join(context_parts)

    async def emit_thinking(self, message: str, node_name: str | None = None) -> None:
        """Emit a thinking event if SSE callback is set."""
        if self.sse_callback:
            await self.sse_callback("thinking", message, node_name)
