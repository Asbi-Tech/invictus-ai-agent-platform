"""Multi-agent graph state schema."""

from datetime import datetime
from typing import Annotated, Any, Callable, Awaitable, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


# Type alias for SSE callback
SSECallbackType = Callable[[str, str | dict, str | None], Awaitable[None]]


class IntentAnalysis(TypedDict, total=False):
    """Result of intent analysis."""

    request_type: str  # "ask" | "create" | "edit" | "extend"
    document_type: str | None  # "prescreening" | "investment_memo" | "custom_report" | None
    entities_detected: list[str]  # List of entity types found (opportunity, client, etc.)
    missing_inputs: list[str]  # List of required but missing inputs
    clarification_needed: bool  # Whether clarification is required
    confidence: float  # Confidence score (0-1)


class ClarificationQuestion(TypedDict):
    """A clarification question to ask the user."""

    question_id: str
    question: str
    options: list[str] | None  # Optional predefined options
    required: bool


class SectionPlan(TypedDict):
    """Plan for a single section."""

    id: str
    name: str
    description: str
    data_sources: list[str]  # Which data sources are needed
    template_section: str | None  # Reference to template section if applicable


class DataRequirement(TypedDict):
    """A data requirement for the execution plan."""

    source: str  # "mcp" | "rag" | "web"
    domain: str | None  # For MCP: "deals", "clients", etc.
    query: str  # Query or tool name
    priority: int  # Execution priority (lower = higher priority)
    purpose: str  # Why this data is needed


class ToolUsage(TypedDict):
    """Planned tool usage."""

    tool: str  # Tool name
    purpose: str  # Why this tool is being called
    order: int  # Execution order


class ExecutionPlan(TypedDict, total=False):
    """Execution plan for document generation."""

    plan_id: str
    sections: list[SectionPlan]
    data_requirements: list[DataRequirement]
    tool_usage_plan: list[ToolUsage]
    template_strategy: str  # "use_existing" | "modify" | "generate_new"
    estimated_complexity: str  # "simple" | "moderate" | "complex"
    created_at: str


class SectionAssignment(TypedDict, total=False):
    """Assignment for section writing."""

    section_id: str
    section_name: str
    status: str  # "pending" | "in_progress" | "completed" | "failed"
    assigned_data: list[str]  # Keys from working_memory to use
    template_section: str | None
    content: str | None
    sources: list[dict[str, Any]]  # Source references
    error: str | None


class SourceRef(TypedDict, total=False):
    """Reference to a source."""

    source_id: str
    source_type: str  # "mcp" | "rag" | "web"
    title: str | None
    url: str | None
    document_id: str | None
    chunk_id: str | None
    confidence: float
    metadata: dict[str, Any]


class ReviewIssue(TypedDict):
    """An issue found during review."""

    issue_type: str  # "coherence" | "citation" | "terminology" | "redundancy"
    severity: str  # "low" | "medium" | "high"
    section_id: str | None
    description: str
    suggestion: str | None


class ReviewResult(TypedDict, total=False):
    """Result of the review process."""

    coherence_score: float
    issues: list[ReviewIssue]
    suggestions: list[str]
    approved: bool


class SourceLedger(TypedDict, total=False):
    """Comprehensive source attribution ledger."""

    sources: list[SourceRef]
    section_mappings: dict[str, list[str]]  # section_id -> list of source_ids
    confidence_scores: dict[str, float]  # source_id -> confidence


class PhaseTransition(TypedDict):
    """Record of a phase transition."""

    from_phase: str
    to_phase: str
    timestamp: str
    reason: str | None


class SynthesizedInsights(TypedDict, total=False):
    """Result of data synthesis."""

    normalized_data: dict[str, Any]
    insights: list[dict[str, Any]]  # Key insights extracted
    data_gaps: list[str]  # Missing data points
    contradictions: list[dict[str, Any]]  # Conflicting information
    confidence_scores: dict[str, float]  # Data point -> confidence


class MultiAgentState(TypedDict, total=False):
    """
    State schema for the multi-agent graph.

    This extends the original GraphState with additional fields for:
    - Intent analysis and clarification
    - Execution planning and confirmation
    - Structured data from multiple sources
    - Synthesis and template management
    - Section-level generation and review
    - Source attribution
    """

    # ==========================================
    # Identity (unchanged from original)
    # ==========================================
    tenant_id: str
    user_id: str
    session_id: str
    module_id: str

    # ==========================================
    # Request Classification (enhanced)
    # ==========================================
    request_type: str  # "ask" | "create" | "edit" | "extend"
    document_type: str | None  # "prescreening" | "investment_memo" | "custom_report"
    agent_case: str | None  # Deprecated, use request_type instead

    # ==========================================
    # Conversation
    # ==========================================
    messages: Annotated[list[BaseMessage], add_messages]
    additional_prompt: str | None

    # ==========================================
    # Intent Analysis Output
    # ==========================================
    intent_analysis: IntentAnalysis | None

    # ==========================================
    # Clarification State (HITL)
    # ==========================================
    clarification_pending: bool
    clarification_questions: list[ClarificationQuestion]
    clarification_responses: dict[str, Any]  # question_id -> response
    hitl_wait_reason: str | None  # "clarification" | "confirmation" | None

    # ==========================================
    # Execution Plan
    # ==========================================
    execution_plan: ExecutionPlan | None
    plan_confirmed: bool
    plan_confirmation_response: str | None  # "approved" | "modify" | "cancelled"
    plan_modifications_requested: list[str]

    # ==========================================
    # Context (unchanged from original)
    # ==========================================
    page_context: dict[str, Any] | None
    document_ids: list[str]
    selected_docs: dict[str, Any]
    current_artifact: dict[str, Any] | None

    # ==========================================
    # Structured Data by Source
    # ==========================================
    mcp_data: dict[str, Any]  # domain -> data from MCP tools
    rag_data: dict[str, Any]  # query_id -> results with citations
    web_data: dict[str, Any]  # query -> results with URLs

    # ==========================================
    # Synthesis & Templates
    # ==========================================
    synthesized_insights: SynthesizedInsights | None
    template_strategy: str  # "use_existing" | "modify" | "generate_new"
    selected_template: dict[str, Any] | None
    template_mapping: dict[str, str]  # section_id -> data_source_key

    # ==========================================
    # Section Writing
    # ==========================================
    section_assignments: list[SectionAssignment]
    sections_completed: int
    sections_total: int

    # ==========================================
    # Review & Sources
    # ==========================================
    review_result: ReviewResult | None
    source_ledger: SourceLedger

    # ==========================================
    # Working State (from original)
    # ==========================================
    current_intent: str | None
    working_memory: dict[str, Any]
    tool_results: list[dict[str, Any]]
    tool_policy: dict[str, Any]
    edit_instructions: list[dict[str, Any]]

    # ==========================================
    # Artifacts (from original)
    # ==========================================
    artifacts: list[dict[str, Any]]
    current_artifact_id: str | None

    # ==========================================
    # Execution Tracking
    # ==========================================
    current_phase: str  # "intent" | "clarification" | "planning" | "confirmation" | "retrieval" | "synthesis" | "template" | "generation" | "review" | "complete"
    phase_history: list[PhaseTransition]

    # ==========================================
    # Streaming & Callbacks
    # ==========================================
    sse_callback: SSECallbackType | None

    # ==========================================
    # Metadata
    # ==========================================
    created_at: datetime
    updated_at: datetime
    tool_call_count: int
    error_count: int


def create_initial_state(
    tenant_id: str,
    user_id: str,
    session_id: str,
    module_id: str = "deals",
    **kwargs: Any,
) -> MultiAgentState:
    """
    Create an initial multi-agent state with defaults.

    Args:
        tenant_id: Tenant identifier
        user_id: User identifier
        session_id: Session identifier
        module_id: Module identifier (default: "deals")
        **kwargs: Additional state fields to set

    Returns:
        Initialized MultiAgentState
    """
    now = datetime.utcnow()

    state: MultiAgentState = {
        # Identity
        "tenant_id": tenant_id,
        "user_id": user_id,
        "session_id": session_id,
        "module_id": module_id,
        # Request
        "request_type": "ask",
        "document_type": None,
        "agent_case": None,
        # Conversation
        "messages": [],
        "additional_prompt": None,
        # Intent
        "intent_analysis": None,
        # Clarification
        "clarification_pending": False,
        "clarification_questions": [],
        "clarification_responses": {},
        "hitl_wait_reason": None,
        # Plan
        "execution_plan": None,
        "plan_confirmed": False,
        "plan_confirmation_response": None,
        "plan_modifications_requested": [],
        # Context
        "page_context": None,
        "document_ids": [],
        "selected_docs": {},
        "current_artifact": None,
        # Data
        "mcp_data": {},
        "rag_data": {},
        "web_data": {},
        # Synthesis
        "synthesized_insights": None,
        "template_strategy": "generate_new",
        "selected_template": None,
        "template_mapping": {},
        # Sections
        "section_assignments": [],
        "sections_completed": 0,
        "sections_total": 0,
        # Review
        "review_result": None,
        "source_ledger": {"sources": [], "section_mappings": {}, "confidence_scores": {}},
        # Working
        "current_intent": None,
        "working_memory": {},
        "tool_results": [],
        "tool_policy": {
            "web_search_enabled": False,
            "rag_enabled": True,
            "enabled_mcps": ["deals"],
            "max_tool_calls": 10,
        },
        "edit_instructions": [],
        # Artifacts
        "artifacts": [],
        "current_artifact_id": None,
        # Execution
        "current_phase": "intent",
        "phase_history": [],
        # Streaming
        "sse_callback": None,
        # Metadata
        "created_at": now,
        "updated_at": now,
        "tool_call_count": 0,
        "error_count": 0,
    }

    # Apply any additional kwargs
    for key, value in kwargs.items():
        if key in state:
            state[key] = value  # type: ignore

    return state
