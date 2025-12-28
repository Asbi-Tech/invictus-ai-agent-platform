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
    FILL = "fill"


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


class TemplateField(BaseModel):
    """Definition of a template field to fill."""

    description: str = Field(description="What this field represents")
    instruction: str = Field(description="How to fill this field")
    type: str = Field(
        default="string",
        description="Field type: string, number, boolean, object, array",
    )
    options: list[str] | None = Field(
        default=None, description="Allowed values for this field (for enum-like fields)"
    )
    required: bool = Field(default=True, description="Whether this field is required")


class TemplateRequest(BaseModel):
    """Template structure for agent to follow.

    Supports both flat and nested structures:
    - Flat: {"field_name": TemplateField}
    - Nested: {"section": {"field_name": TemplateField}}
    """

    fields: dict[str, TemplateField | dict[str, TemplateField]] = Field(
        description="Template fields to fill, can be flat or nested"
    )


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

    # Template (for create/fill modes)
    template: TemplateRequest | None = Field(
        default=None,
        description="Template structure for agent to follow (for create/fill modes)",
    )

    # Resume field (for continuing paused sessions)
    # When session_id is provided and session is paused, this field enables resume
    # Use 'message' field for the actual user input (clarification answers, modifications, etc.)
    confirmation_response: str | None = Field(
        default=None,
        description="Resume response: 'clarified', 'approved', 'modify', or 'cancelled'",
    )


class ResumeRequest(BaseModel):
    """Request to resume a paused execution with user input.

    Note: This is now handled through UnifiedChatRequest with session_id + confirmation_response.
    Kept for backward compatibility documentation.
    """

    session_id: str = Field(description="Session ID of the paused execution")
    message: str = Field(
        default="",
        description="User's input (clarification answers, modification requests, etc.)",
    )
    confirmation_response: str | None = Field(
        default=None,
        description="Resume response: 'clarified', 'approved', 'modify', or 'cancelled'",
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


class ClarificationQuestionResponse(BaseModel):
    """A clarification question in response."""

    question_id: str = Field(description="Unique question identifier")
    question: str = Field(description="The question text")
    options: list[str] | None = Field(default=None, description="Predefined answer options")
    required: bool = Field(default=True, description="Whether an answer is required")


class AgentMessageForUser(BaseModel):
    """Human-readable message for the user.

    Used in agent mode responses to provide user-facing communication
    separate from the structured system output.
    """

    type: str = Field(
        description="Message type: 'plan', 'summary', 'clarification', 'progress', 'error'"
    )
    content: str = Field(description="Human-readable message content")
    plan_summary: dict[str, Any] | None = Field(
        default=None,
        description="Structured plan summary if type is 'plan'",
    )
    questions: list[ClarificationQuestionResponse] | None = Field(
        default=None,
        description="Clarification questions if type is 'clarification'",
    )


class AgentOutputForSystem(BaseModel):
    """Structured output for backend system processing.

    Provides machine-readable data for the backend to process,
    separate from the user-facing message.
    """

    operation: str = Field(
        description="Operation type: 'create', 'edit', 'fill', 'notify'"
    )
    artifact: ArtifactResponse | None = Field(
        default=None,
        description="Generated artifact (for create operation)",
    )
    edit_instructions: list["EditInstruction"] | None = Field(
        default=None,
        description="Edit instructions (for edit operation)",
    )
    filled_template: dict[str, Any] | None = Field(
        default=None,
        description="Filled template values mirroring input structure (for fill operation)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (word count, sections count, etc.)",
    )


class HITLStatus(BaseModel):
    """HITL interrupt status when execution is paused for user input."""

    paused: bool = Field(description="Whether execution is paused")
    interrupt_type: str = Field(description="Type of interrupt: 'clarification' or 'confirmation'")
    resume_endpoint: str = Field(description="Endpoint to call to resume execution")
    plan: dict[str, Any] | None = Field(
        default=None, description="Execution plan (for confirmation interrupts)"
    )
    questions: list[dict[str, Any]] | None = Field(
        default=None, description="Clarification questions (for clarification interrupts)"
    )
    missing_inputs: list[str] | None = Field(
        default=None, description="List of missing inputs that need clarification"
    )


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
    # HITL status (when execution is paused for user input)
    hitl_status: HITLStatus | None = Field(
        default=None, description="HITL status when execution is paused for user input"
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

    # === Connection & Status Events ===
    STATUS = "status"
    THINKING = "thinking"  # Intermediate thought status events
    FINAL = "final"
    ERROR = "error"

    # === Tool Events ===
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_RESULT = "tool_call_result"

    # === Response Streaming Events ===
    ASSISTANT_DELTA = "assistant_delta"
    ARTIFACT_UPDATE = "artifact_update"
    EDIT_INSTRUCTION = "edit_instruction"  # For streaming edit instructions

    # === HITL Events ===
    HITL_REQUEST = "hitl_request"
    CLARIFICATION_REQUIRED = "clarification_required"
    CLARIFICATION_RESOLVED = "clarification_resolved"
    PLAN_GENERATED = "plan_generated"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    CONFIRMATION_RECEIVED = "confirmation_received"

    # === Phase Lifecycle Events ===
    PHASE_STARTED = "phase_started"
    PHASE_COMPLETED = "phase_completed"
    INTENT_DETECTED = "intent_detected"
    ENTITIES_DETECTED = "entities_detected"

    # === Data Retrieval Events ===
    FETCHING_MCP_DATA = "fetching_mcp_data"
    MCP_DATA_RECEIVED = "mcp_data_received"
    FETCHING_RAG_DATA = "fetching_rag_data"
    RAG_DATA_RECEIVED = "rag_data_received"
    FETCHING_WEB_DATA = "fetching_web_data"
    WEB_DATA_RECEIVED = "web_data_received"

    # === Synthesis Events ===
    SYNTHESIS_STARTED = "synthesis_started"
    INSIGHT_GENERATED = "insight_generated"
    SYNTHESIS_COMPLETED = "synthesis_completed"

    # === Template Events ===
    TEMPLATE_SELECTED = "template_selected"
    TEMPLATE_ADAPTED = "template_adapted"

    # === Section Generation Events ===
    SECTION_STARTED = "section_started"
    SECTION_PROGRESS = "section_progress"
    SECTION_COMPLETED = "section_completed"

    # === Review Events ===
    REVIEW_STARTED = "review_started"
    REVIEW_ISSUE_FOUND = "review_issue_found"
    REVIEW_COMPLETED = "review_completed"

    # === Source Attribution Events ===
    SOURCE_MAPPED = "source_mapped"


class SSEEvent(BaseModel):
    """Server-Sent Event payload."""

    event_type: SSEEventType
    data: dict[str, Any]
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    def to_sse_format(self) -> str:
        """Convert to SSE wire format."""
        import json

        return f"event: {self.event_type.value}\ndata: {json.dumps(self.model_dump(mode='json'))}\n\n"
