"""API request/response schemas."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ============================================================
# Enums
# ============================================================


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


# ============================================================
# Request Schemas
# ============================================================


class PageContextRequest(BaseModel):
    """Page context from the UI."""

    module_id: str = Field(
        default="deals", description="Module identifier (deals, crm, risk, client_portal)"
    )
    screen_name: str = Field(description="Current screen name")
    opportunity_id: str | None = Field(default=None, description="Opportunity identifier")
    opportunity_name: str | None = Field(default=None, description="Opportunity name")
    screen_highlights: dict[str, Any] = Field(
        default_factory=dict, description="Module-specific screen highlights"
    )
    additional_context: dict[str, Any] = Field(
        default_factory=dict, description="Additional context data"
    )


class StorageConfigRequest(BaseModel):
    """Azure Blob Storage configuration for document access."""

    account_url: str = Field(description="Azure Blob Storage account URL")
    filesystem: str = Field(default="documents", description="Filesystem name")
    base_prefix: str = Field(description="Base path prefix for documents")


class DocumentSelectionRequest(BaseModel):
    """Selected documents for RAG operations."""

    doc_ids: list[str] = Field(default_factory=list, description="List of document IDs")
    doc_sets: list[str] = Field(
        default_factory=list, description="Document set names to include"
    )
    storage: StorageConfigRequest | None = Field(
        default=None, description="Storage config for MVP testing"
    )


class ArtifactInput(BaseModel):
    """Current artifact being edited (for agent edit mode)."""

    artifact_id: str = Field(description="Unique artifact identifier")
    artifact_type: str = Field(description="Type: memo, report, strategy_doc, summary")
    title: str = Field(description="Artifact title")
    content: str = Field(description="Markdown content of the artifact")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class UnifiedChatRequest(BaseModel):
    """Chat request supporting both ask and agent modes."""

    # Core identifiers
    tenant_id: str = Field(description="Tenant identifier")
    module_id: str = Field(default="deals", description="Module identifier")
    user_id: str = Field(description="User identifier")

    # Message content
    message: str = Field(description="The user's message")
    additional_prompt: str | None = Field(
        default=None,
        description="Extra user context (e.g., 'This is for a board meeting')",
    )

    # Context
    page_context: PageContextRequest | None = Field(
        default=None, description="Current page context with opportunity details"
    )
    document_ids: list[str] = Field(
        default_factory=list,
        description="[DEPRECATED] Use selected_docs instead. Document IDs for RAG context",
    )
    selected_docs: DocumentSelectionRequest | None = Field(
        default=None, description="Selected documents with storage config for RAG"
    )

    # Session (for ask mode continuity)
    session_id: str | None = Field(
        default=None, description="Session ID for conversational continuity"
    )

    # Request type configuration
    type: RequestType = Field(
        default=RequestType.ASK, description="Request type: ask or agent"
    )
    agent_case: AgentCase | None = Field(
        default=None, description="For agent type: edit or create"
    )

    # Agent mode specific
    current_artifact: ArtifactInput | None = Field(
        default=None, description="Artifact to edit (for agent edit mode)"
    )

    # Tool enablement
    enabled_mcps: list[str] = Field(
        default_factory=lambda: ["deals"],
        description="List of enabled MCP server names",
    )
    web_search_enabled: bool = Field(
        default=False, description="Enable web search"
    )


# ============================================================
# Response Schemas
# ============================================================


class ToolResultResponse(BaseModel):
    """Tool result in response."""

    tool_name: str
    input_summary: str
    output_summary: str
    latency_ms: float
    success: bool
    citations: list[dict[str, Any]] = Field(default_factory=list)


class EditInstruction(BaseModel):
    """Single edit instruction for artifact modification (diff-based)."""

    operation: EditOperation = Field(description="Operation type: add, remove, modify")
    section_id: str | None = Field(default=None, description="Section identifier")
    section_title: str | None = Field(default=None, description="Human-readable section name")
    position: str | None = Field(
        default=None, description="Position: before, after, or replace"
    )
    content: str | None = Field(default=None, description="New or modified content")
    reasoning: str = Field(description="Why this change is needed")


class ArtifactResponse(BaseModel):
    """Generated artifact in response."""

    artifact_id: str
    artifact_type: str
    title: str
    content: str
    version: int = 1
    citations: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ChatResponse(BaseModel):
    """Chat response payload - extended for both ask and agent modes."""

    session_id: str
    message: str
    tool_results: list[ToolResultResponse] = Field(default_factory=list)
    citations: list[dict[str, Any]] = Field(default_factory=list)
    intent: str | None = None
    # Agent mode response fields
    artifact: ArtifactResponse | None = Field(
        default=None, description="Generated artifact (for agent create mode)"
    )
    edit_instructions: list[EditInstruction] | None = Field(
        default=None, description="Edit instructions (for agent edit mode)"
    )


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    environment: str


class ErrorResponse(BaseModel):
    """Error response."""

    error: str
    detail: str | None = None
    request_id: str | None = None


# ============================================================
# SSE Event Types
# ============================================================


class SSEEventType(str, Enum):
    """Types of Server-Sent Events."""

    STATUS = "status"
    THINKING = "thinking"  # Intermediate thought status events
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_RESULT = "tool_call_result"
    ASSISTANT_DELTA = "assistant_delta"
    ARTIFACT_UPDATE = "artifact_update"
    EDIT_INSTRUCTION = "edit_instruction"  # For streaming edit instructions
    HITL_REQUEST = "hitl_request"
    FINAL = "final"
    ERROR = "error"


class SSEEvent(BaseModel):
    """Server-Sent Event payload."""

    event_type: SSEEventType
    data: dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    def to_sse_format(self) -> str:
        """Convert to SSE wire format."""
        import json

        return f"event: {self.event_type.value}\ndata: {json.dumps(self.model_dump(mode='json'))}\n\n"
