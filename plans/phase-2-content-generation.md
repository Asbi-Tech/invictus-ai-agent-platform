# Phase 2: Content Generation + Artifact Storage

## Objectives

- Build a report generation subgraph for creating memos, strategy docs, and reports
- Implement artifact storage with versioning in Cosmos DB
- Add edit flow for modifying existing artifacts
- Create citation bundling and tracking system

## Prerequisites

- Phase 1 completed (core agent, streaming, Cosmos checkpointer)
- Agent API running and tested
- Cosmos DB artifacts container created

---

## Implementation Tasks

### Task 2.1: Define Artifact Schema

**packages/agent_core/src/agent_core/state/artifacts.py**
```python
"""Artifact models for content generation."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ArtifactType(str, Enum):
    """Types of artifacts that can be generated."""
    MEMO = "memo"
    INVESTMENT_REPORT = "investment_report"
    STRATEGY_DOC = "strategy_doc"
    SUMMARY = "summary"
    COMPARISON = "comparison"
    CUSTOM = "custom"


class ArtifactSection(BaseModel):
    """A section within an artifact."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    content: str
    order: int
    citations: list[dict[str, Any]] = Field(default_factory=list)


class Citation(BaseModel):
    """A citation to a source document."""
    citation_id: str = Field(default_factory=lambda: str(uuid4()))
    doc_id: str
    doc_name: str
    chunk_id: str | None = None
    page_number: int | None = None
    excerpt: str | None = None
    source_type: str = "document"  # document, mcp_tool, web


class ArtifactMetadata(BaseModel):
    """Metadata for an artifact."""
    title: str
    artifact_type: ArtifactType
    description: str | None = None
    audience: str | None = None  # e.g., "investor", "internal", "board"
    timeframe: str | None = None  # e.g., "Q4 2024", "YTD"
    currency: str | None = None
    benchmark: str | None = None
    tags: list[str] = Field(default_factory=list)


class Artifact(BaseModel):
    """Complete artifact model."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    tenant_id: str
    user_id: str
    session_id: str

    metadata: ArtifactMetadata
    sections: list[ArtifactSection] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)

    # Versioning
    version: int = 1
    parent_version_id: str | None = None
    is_latest: bool = True

    # Content
    content_markdown: str = ""  # Full rendered markdown

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Status
    status: str = "draft"  # draft, final, archived


class ArtifactVersion(BaseModel):
    """Lightweight version reference."""
    version_id: str
    version: int
    created_at: datetime
    created_by: str
    change_summary: str | None = None
```

---

### Task 2.2: Build Artifact Storage

**packages/agent_core/src/agent_core/memory/artifact_store.py**
```python
"""Artifact storage using Cosmos DB."""

from datetime import datetime
from typing import Optional

from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError

from agent_core.state.artifacts import Artifact, ArtifactVersion
from common.errors import InvictusError
from common.logging import get_logger

logger = get_logger(__name__)


class ArtifactNotFoundError(InvictusError):
    """Artifact not found in storage."""
    pass


class ArtifactStore:
    """Store and retrieve artifacts from Cosmos DB."""

    def __init__(
        self,
        endpoint: str,
        key: str,
        database_name: str,
        container_name: str = "artifacts",
    ):
        self.client = CosmosClient(endpoint, credential=key)
        self.database = self.client.get_database_client(database_name)
        self.container = self.database.get_container_client(container_name)

    async def save(self, artifact: Artifact) -> Artifact:
        """
        Save an artifact to Cosmos DB.

        If the artifact already exists, creates a new version.
        """
        artifact.updated_at = datetime.utcnow()

        # Check if this is an update
        existing = await self.get_by_id(artifact.id, artifact.tenant_id)

        if existing:
            # Mark old version as not latest
            existing.is_latest = False
            self.container.upsert_item(existing.model_dump())

            # Increment version
            artifact.version = existing.version + 1
            artifact.parent_version_id = f"{existing.id}:v{existing.version}"

        # Save the artifact
        doc = {
            "id": f"{artifact.id}:v{artifact.version}",
            "artifact_id": artifact.id,
            "tenant_id": artifact.tenant_id,
            **artifact.model_dump(),
        }

        self.container.upsert_item(doc)

        logger.info(
            "Saved artifact",
            artifact_id=artifact.id,
            version=artifact.version,
            tenant_id=artifact.tenant_id,
        )

        return artifact

    async def get_by_id(
        self,
        artifact_id: str,
        tenant_id: str,
        version: Optional[int] = None,
    ) -> Optional[Artifact]:
        """
        Get an artifact by ID.

        If version is not specified, returns the latest version.
        """
        try:
            if version:
                doc_id = f"{artifact_id}:v{version}"
                item = self.container.read_item(item=doc_id, partition_key=tenant_id)
            else:
                # Get latest version
                query = """
                    SELECT TOP 1 * FROM c
                    WHERE c.artifact_id = @artifact_id
                    AND c.tenant_id = @tenant_id
                    AND c.is_latest = true
                """
                items = list(self.container.query_items(
                    query=query,
                    parameters=[
                        {"name": "@artifact_id", "value": artifact_id},
                        {"name": "@tenant_id", "value": tenant_id},
                    ],
                    partition_key=tenant_id,
                ))
                if not items:
                    return None
                item = items[0]

            return Artifact(**item)

        except CosmosResourceNotFoundError:
            return None

    async def list_versions(
        self,
        artifact_id: str,
        tenant_id: str,
    ) -> list[ArtifactVersion]:
        """List all versions of an artifact."""
        query = """
            SELECT c.id, c.version, c.created_at, c.user_id, c.metadata.title
            FROM c
            WHERE c.artifact_id = @artifact_id
            AND c.tenant_id = @tenant_id
            ORDER BY c.version DESC
        """

        items = self.container.query_items(
            query=query,
            parameters=[
                {"name": "@artifact_id", "value": artifact_id},
                {"name": "@tenant_id", "value": tenant_id},
            ],
            partition_key=tenant_id,
        )

        versions = []
        for item in items:
            versions.append(ArtifactVersion(
                version_id=item["id"],
                version=item["version"],
                created_at=item["created_at"],
                created_by=item["user_id"],
            ))

        return versions

    async def list_by_tenant(
        self,
        tenant_id: str,
        artifact_type: Optional[str] = None,
        limit: int = 50,
    ) -> list[Artifact]:
        """List artifacts for a tenant."""
        if artifact_type:
            query = """
                SELECT * FROM c
                WHERE c.tenant_id = @tenant_id
                AND c.is_latest = true
                AND c.metadata.artifact_type = @artifact_type
                ORDER BY c.updated_at DESC
            """
            params = [
                {"name": "@tenant_id", "value": tenant_id},
                {"name": "@artifact_type", "value": artifact_type},
            ]
        else:
            query = """
                SELECT * FROM c
                WHERE c.tenant_id = @tenant_id
                AND c.is_latest = true
                ORDER BY c.updated_at DESC
            """
            params = [{"name": "@tenant_id", "value": tenant_id}]

        items = self.container.query_items(
            query=query,
            parameters=params,
            partition_key=tenant_id,
            max_item_count=limit,
        )

        return [Artifact(**item) for item in items]

    async def delete(self, artifact_id: str, tenant_id: str) -> bool:
        """Delete all versions of an artifact."""
        query = """
            SELECT c.id FROM c
            WHERE c.artifact_id = @artifact_id
            AND c.tenant_id = @tenant_id
        """

        items = list(self.container.query_items(
            query=query,
            parameters=[
                {"name": "@artifact_id", "value": artifact_id},
                {"name": "@tenant_id", "value": tenant_id},
            ],
            partition_key=tenant_id,
        ))

        for item in items:
            self.container.delete_item(item=item["id"], partition_key=tenant_id)

        logger.info("Deleted artifact", artifact_id=artifact_id, versions=len(items))
        return len(items) > 0
```

---

### Task 2.3: Build Report Generation Subgraph

**packages/agent_core/src/agent_core/graph/subgraphs/report_generation.py**
```python
"""Subgraph for generating reports and memos."""

from typing import Any
from uuid import uuid4

from langchain_core.messages import HumanMessage, AIMessage
from langchain_openai import AzureChatOpenAI
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field

from agent_core.state.artifacts import (
    Artifact,
    ArtifactMetadata,
    ArtifactSection,
    ArtifactType,
    Citation,
)
from common.config import get_settings
from common.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class ReportGenerationState(BaseModel):
    """State for report generation subgraph."""
    # Input
    tenant_id: str
    user_id: str
    session_id: str
    request: str  # User's generation request
    context: dict[str, Any] = Field(default_factory=dict)  # Entity data, RAG results

    # Report planning
    report_type: ArtifactType = ArtifactType.MEMO
    outline: list[dict[str, str]] = Field(default_factory=list)  # [{title, description}]
    target_audience: str | None = None
    timeframe: str | None = None

    # Generation progress
    current_section_index: int = 0
    sections: list[ArtifactSection] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)

    # Output
    artifact: Artifact | None = None
    error: str | None = None


OUTLINE_PROMPT = """You are generating an outline for a {report_type}.

User request: {request}

Available context:
{context}

Generate a structured outline with 3-6 sections. For each section, provide:
- title: Section heading
- description: Brief description of what this section should cover

Respond in JSON format:
{{
  "report_type": "memo|investment_report|strategy_doc|summary",
  "title": "Title for the document",
  "target_audience": "investor|internal|board|client",
  "sections": [
    {{"title": "Section Title", "description": "What to cover"}}
  ]
}}
"""

SECTION_PROMPT = """You are writing section {section_num} of a {report_type}.

Document title: {title}
Section: {section_title}
Section guidance: {section_description}
Target audience: {audience}

Context and data:
{context}

Previous sections (for continuity):
{previous_sections}

Write the content for this section. Use markdown formatting.
Include citations as [1], [2], etc. when referencing specific data or documents.

After your content, list any citations used in this format:
CITATIONS:
[1] Source name - relevant excerpt
[2] Source name - relevant excerpt
"""


async def plan_outline(state: ReportGenerationState) -> dict:
    """Create an outline for the report."""
    llm = AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        deployment_name=settings.azure_openai_deployment_name,
        temperature=0.7,
    )

    context_str = "\n".join([
        f"- {k}: {str(v)[:500]}"
        for k, v in state.context.items()
    ])

    prompt = OUTLINE_PROMPT.format(
        report_type=state.report_type.value,
        request=state.request,
        context=context_str or "No additional context provided.",
    )

    response = await llm.ainvoke([HumanMessage(content=prompt)])

    try:
        import json
        outline_data = json.loads(response.content)

        return {
            "report_type": ArtifactType(outline_data.get("report_type", "memo")),
            "outline": outline_data.get("sections", []),
            "target_audience": outline_data.get("target_audience", "internal"),
        }
    except Exception as e:
        logger.error("Failed to parse outline", error=str(e))
        return {
            "outline": [{"title": "Main Content", "description": state.request}],
        }


async def generate_section(state: ReportGenerationState) -> dict:
    """Generate the next section of the report."""
    if state.current_section_index >= len(state.outline):
        return {}

    llm = AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        deployment_name=settings.azure_openai_deployment_name,
        temperature=0.7,
    )

    current_outline = state.outline[state.current_section_index]

    # Build context string
    context_str = "\n".join([
        f"- {k}: {str(v)[:1000]}"
        for k, v in state.context.items()
    ])

    # Build previous sections summary
    previous_sections = "\n\n".join([
        f"## {s.title}\n{s.content[:300]}..."
        for s in state.sections
    ]) if state.sections else "This is the first section."

    prompt = SECTION_PROMPT.format(
        section_num=state.current_section_index + 1,
        report_type=state.report_type.value,
        title=state.outline[0].get("title", "Report") if state.outline else "Report",
        section_title=current_outline["title"],
        section_description=current_outline.get("description", ""),
        audience=state.target_audience or "internal",
        context=context_str or "No additional context.",
        previous_sections=previous_sections,
    )

    response = await llm.ainvoke([HumanMessage(content=prompt)])
    content = response.content

    # Extract citations from the response
    section_citations = []
    if "CITATIONS:" in content:
        parts = content.split("CITATIONS:")
        content = parts[0].strip()
        citations_text = parts[1] if len(parts) > 1 else ""

        # Parse citations
        import re
        citation_matches = re.findall(r'\[(\d+)\]\s*(.+?)(?=\[\d+\]|$)', citations_text, re.DOTALL)
        for num, citation_text in citation_matches:
            section_citations.append(Citation(
                doc_id=f"ref-{num}",
                doc_name=citation_text.strip()[:100],
                excerpt=citation_text.strip(),
            ))

    new_section = ArtifactSection(
        title=current_outline["title"],
        content=content,
        order=state.current_section_index,
        citations=[c.model_dump() for c in section_citations],
    )

    return {
        "sections": state.sections + [new_section],
        "citations": state.citations + section_citations,
        "current_section_index": state.current_section_index + 1,
    }


def should_continue_generating(state: ReportGenerationState) -> str:
    """Check if we should generate more sections."""
    if state.current_section_index < len(state.outline):
        return "generate_section"
    return "finalize_artifact"


async def finalize_artifact(state: ReportGenerationState) -> dict:
    """Finalize the artifact and create the full document."""
    # Build full markdown content
    title = state.outline[0].get("title", "Report") if state.outline else "Report"

    markdown_parts = [f"# {title}\n"]

    for section in state.sections:
        markdown_parts.append(f"\n## {section.title}\n\n{section.content}\n")

    if state.citations:
        markdown_parts.append("\n---\n## References\n")
        for i, citation in enumerate(state.citations, 1):
            markdown_parts.append(f"\n[{i}] {citation.doc_name}")

    content_markdown = "\n".join(markdown_parts)

    artifact = Artifact(
        tenant_id=state.tenant_id,
        user_id=state.user_id,
        session_id=state.session_id,
        metadata=ArtifactMetadata(
            title=title,
            artifact_type=state.report_type,
            audience=state.target_audience,
            timeframe=state.timeframe,
        ),
        sections=state.sections,
        citations=state.citations,
        content_markdown=content_markdown,
        status="draft",
    )

    logger.info(
        "Finalized artifact",
        artifact_id=artifact.id,
        sections=len(state.sections),
        citations=len(state.citations),
    )

    return {"artifact": artifact}


def create_report_generation_graph() -> StateGraph:
    """Create the report generation subgraph."""
    graph = StateGraph(ReportGenerationState)

    graph.add_node("plan_outline", plan_outline)
    graph.add_node("generate_section", generate_section)
    graph.add_node("finalize_artifact", finalize_artifact)

    graph.set_entry_point("plan_outline")
    graph.add_edge("plan_outline", "generate_section")
    graph.add_conditional_edges(
        "generate_section",
        should_continue_generating,
        {
            "generate_section": "generate_section",
            "finalize_artifact": "finalize_artifact",
        },
    )
    graph.add_edge("finalize_artifact", END)

    return graph
```

---

### Task 2.4: Build Edit Subgraph

**packages/agent_core/src/agent_core/graph/subgraphs/edit_artifact.py**
```python
"""Subgraph for editing existing artifacts."""

from typing import Any

from langchain_core.messages import HumanMessage
from langchain_openai import AzureChatOpenAI
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field

from agent_core.state.artifacts import Artifact, ArtifactSection
from common.config import get_settings
from common.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class EditArtifactState(BaseModel):
    """State for artifact editing subgraph."""
    # Input
    tenant_id: str
    user_id: str
    session_id: str

    artifact: Artifact
    edit_request: str
    section_index: int | None = None  # If editing a specific section

    # Output
    updated_artifact: Artifact | None = None
    error: str | None = None


EDIT_SECTION_PROMPT = """You are editing a section of a document.

Original section:
Title: {section_title}
Content:
{original_content}

Edit request: {edit_request}

Rewrite the section according to the edit request. Maintain the same general structure and citations where appropriate.
Return only the new content for this section.
"""

EDIT_FULL_PROMPT = """You are editing a document.

Document title: {title}
Document type: {artifact_type}

Current content:
{content}

Edit request: {edit_request}

Apply the requested changes and return the full updated document in markdown format.
Maintain the existing structure where possible.
"""


async def analyze_edit_request(state: EditArtifactState) -> dict:
    """Analyze the edit request to determine scope."""
    # Simple heuristic: if request mentions a section number or title, edit that section
    edit_lower = state.edit_request.lower()

    for i, section in enumerate(state.artifact.sections):
        if section.title.lower() in edit_lower or f"section {i+1}" in edit_lower:
            return {"section_index": i}

    # Full document edit
    return {"section_index": None}


async def edit_section(state: EditArtifactState) -> dict:
    """Edit a specific section."""
    if state.section_index is None or state.section_index >= len(state.artifact.sections):
        return {"error": "Invalid section index"}

    llm = AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        deployment_name=settings.azure_openai_deployment_name,
        temperature=0.7,
    )

    section = state.artifact.sections[state.section_index]

    prompt = EDIT_SECTION_PROMPT.format(
        section_title=section.title,
        original_content=section.content,
        edit_request=state.edit_request,
    )

    response = await llm.ainvoke([HumanMessage(content=prompt)])

    # Create updated section
    updated_section = ArtifactSection(
        id=section.id,
        title=section.title,
        content=response.content,
        order=section.order,
        citations=section.citations,
    )

    # Update sections list
    updated_sections = list(state.artifact.sections)
    updated_sections[state.section_index] = updated_section

    # Rebuild markdown
    markdown_parts = [f"# {state.artifact.metadata.title}\n"]
    for s in updated_sections:
        markdown_parts.append(f"\n## {s.title}\n\n{s.content}\n")

    # Create updated artifact
    updated_artifact = state.artifact.model_copy(update={
        "sections": updated_sections,
        "content_markdown": "\n".join(markdown_parts),
    })

    return {"updated_artifact": updated_artifact}


async def edit_full_document(state: EditArtifactState) -> dict:
    """Edit the full document."""
    llm = AzureChatOpenAI(
        azure_endpoint=settings.azure_openai_endpoint,
        api_key=settings.azure_openai_api_key,
        api_version=settings.azure_openai_api_version,
        deployment_name=settings.azure_openai_deployment_name,
        temperature=0.7,
    )

    prompt = EDIT_FULL_PROMPT.format(
        title=state.artifact.metadata.title,
        artifact_type=state.artifact.metadata.artifact_type.value,
        content=state.artifact.content_markdown,
        edit_request=state.edit_request,
    )

    response = await llm.ainvoke([HumanMessage(content=prompt)])

    # Parse the response back into sections
    new_content = response.content
    sections = []

    import re
    section_matches = re.findall(r'##\s+(.+?)\n(.*?)(?=##|\Z)', new_content, re.DOTALL)

    for i, (title, content) in enumerate(section_matches):
        sections.append(ArtifactSection(
            title=title.strip(),
            content=content.strip(),
            order=i,
        ))

    updated_artifact = state.artifact.model_copy(update={
        "sections": sections,
        "content_markdown": new_content,
    })

    return {"updated_artifact": updated_artifact}


def route_edit_type(state: EditArtifactState) -> str:
    """Route to appropriate edit function."""
    if state.section_index is not None:
        return "edit_section"
    return "edit_full_document"


def create_edit_artifact_graph() -> StateGraph:
    """Create the edit artifact subgraph."""
    graph = StateGraph(EditArtifactState)

    graph.add_node("analyze_edit_request", analyze_edit_request)
    graph.add_node("edit_section", edit_section)
    graph.add_node("edit_full_document", edit_full_document)

    graph.set_entry_point("analyze_edit_request")
    graph.add_conditional_edges(
        "analyze_edit_request",
        route_edit_type,
        {
            "edit_section": "edit_section",
            "edit_full_document": "edit_full_document",
        },
    )
    graph.add_edge("edit_section", END)
    graph.add_edge("edit_full_document", END)

    return graph
```

---

### Task 2.5: Integrate Generation into Main Graph

**packages/agent_core/src/agent_core/graph/nodes/generate_content.py**
```python
"""Node for content generation in the main graph."""

from datetime import datetime

from agent_core.state.models import AgentState, IntentType, Artifact as StateArtifact
from agent_core.state.artifacts import ArtifactType
from agent_core.graph.subgraphs.report_generation import (
    ReportGenerationState,
    create_report_generation_graph,
)
from agent_core.graph.subgraphs.edit_artifact import (
    EditArtifactState,
    create_edit_artifact_graph,
)
from agent_core.memory.artifact_store import ArtifactStore
from common.config import get_settings
from common.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


async def generate_content(state: AgentState) -> dict:
    """
    Generate content based on user intent.

    For GENERATE intent: Creates new artifacts
    For EDIT intent: Modifies existing artifacts
    """
    if state.current_intent == IntentType.GENERATE:
        return await _handle_generate(state)
    elif state.current_intent == IntentType.EDIT:
        return await _handle_edit(state)

    return {}


async def _handle_generate(state: AgentState) -> dict:
    """Handle content generation."""
    # Get the user's request
    last_message = state.messages[-1].content if state.messages else ""

    # Determine artifact type from request
    request_lower = last_message.lower()
    if "memo" in request_lower:
        artifact_type = ArtifactType.MEMO
    elif "report" in request_lower:
        artifact_type = ArtifactType.INVESTMENT_REPORT
    elif "strategy" in request_lower:
        artifact_type = ArtifactType.STRATEGY_DOC
    elif "summary" in request_lower:
        artifact_type = ArtifactType.SUMMARY
    else:
        artifact_type = ArtifactType.MEMO

    # Build context from working memory
    context = {
        **state.working_memory,
    }

    # Create subgraph state
    gen_state = ReportGenerationState(
        tenant_id=state.tenant_id,
        user_id=state.user_id,
        session_id=state.session_id,
        request=last_message,
        context=context,
        report_type=artifact_type,
        timeframe=state.working_memory.get("timeframe"),
    )

    # Run the generation subgraph
    gen_graph = create_report_generation_graph().compile()
    result = await gen_graph.ainvoke(gen_state.model_dump())

    if result.get("artifact"):
        artifact = result["artifact"]

        # Save to artifact store
        store = ArtifactStore(
            endpoint=settings.cosmos_endpoint,
            key=settings.cosmos_key,
            database_name=settings.cosmos_database_name,
            container_name=settings.cosmos_artifacts_container,
        )
        saved_artifact = await store.save(artifact)

        # Add to state
        state_artifact = StateArtifact(
            artifact_id=saved_artifact.id,
            artifact_type=saved_artifact.metadata.artifact_type.value,
            title=saved_artifact.metadata.title,
            content=saved_artifact.content_markdown,
            version=saved_artifact.version,
            citations=[c.model_dump() for c in saved_artifact.citations],
        )

        return {
            "artifacts": state.artifacts + [state_artifact],
            "current_artifact_id": saved_artifact.id,
            "working_memory": {
                **state.working_memory,
                "last_artifact_id": saved_artifact.id,
                "last_artifact_title": saved_artifact.metadata.title,
            },
        }

    return {}


async def _handle_edit(state: AgentState) -> dict:
    """Handle content editing."""
    # Get the artifact to edit
    artifact_id = state.current_artifact_id or state.working_memory.get("last_artifact_id")

    if not artifact_id:
        logger.warning("No artifact to edit")
        return {}

    # Load the artifact
    store = ArtifactStore(
        endpoint=settings.cosmos_endpoint,
        key=settings.cosmos_key,
        database_name=settings.cosmos_database_name,
        container_name=settings.cosmos_artifacts_container,
    )

    artifact = await store.get_by_id(artifact_id, state.tenant_id)
    if not artifact:
        logger.warning("Artifact not found", artifact_id=artifact_id)
        return {}

    # Get the edit request
    last_message = state.messages[-1].content if state.messages else ""

    # Create edit state
    edit_state = EditArtifactState(
        tenant_id=state.tenant_id,
        user_id=state.user_id,
        session_id=state.session_id,
        artifact=artifact,
        edit_request=last_message,
    )

    # Run the edit subgraph
    edit_graph = create_edit_artifact_graph().compile()
    result = await edit_graph.ainvoke(edit_state.model_dump())

    if result.get("updated_artifact"):
        updated = result["updated_artifact"]
        saved = await store.save(updated)

        # Update state artifact
        for i, art in enumerate(state.artifacts):
            if art.artifact_id == artifact_id:
                state.artifacts[i] = StateArtifact(
                    artifact_id=saved.id,
                    artifact_type=saved.metadata.artifact_type.value,
                    title=saved.metadata.title,
                    content=saved.content_markdown,
                    version=saved.version,
                    citations=[c.model_dump() for c in saved.citations],
                )
                break

        return {
            "artifacts": state.artifacts,
            "working_memory": {
                **state.working_memory,
                "last_edit_version": saved.version,
            },
        }

    return {}
```

---

### Task 2.6: Add Artifact API Endpoints

**apps/agent_api/src/agent_api/api/artifacts.py**
```python
"""Artifact management API routes."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from agent_core.memory.artifact_store import ArtifactStore, ArtifactNotFoundError
from agent_core.state.artifacts import Artifact, ArtifactVersion
from common.config import get_settings
from common.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter(prefix="/v1/artifacts", tags=["artifacts"])

# Initialize artifact store
artifact_store = ArtifactStore(
    endpoint=settings.cosmos_endpoint,
    key=settings.cosmos_key,
    database_name=settings.cosmos_database_name,
    container_name=settings.cosmos_artifacts_container,
)


class ArtifactSummary(BaseModel):
    """Summary view of an artifact."""
    id: str
    title: str
    artifact_type: str
    version: int
    status: str
    created_at: str
    updated_at: str


class ArtifactListResponse(BaseModel):
    """Response for artifact list."""
    artifacts: list[ArtifactSummary]
    total: int


class ArtifactVersionsResponse(BaseModel):
    """Response for artifact versions."""
    artifact_id: str
    versions: list[ArtifactVersion]


@router.get("", response_model=ArtifactListResponse)
async def list_artifacts(
    tenant_id: str,
    artifact_type: Optional[str] = Query(None),
    limit: int = Query(50, le=100),
) -> ArtifactListResponse:
    """List artifacts for a tenant."""
    artifacts = await artifact_store.list_by_tenant(
        tenant_id=tenant_id,
        artifact_type=artifact_type,
        limit=limit,
    )

    summaries = [
        ArtifactSummary(
            id=a.id,
            title=a.metadata.title,
            artifact_type=a.metadata.artifact_type.value,
            version=a.version,
            status=a.status,
            created_at=a.created_at.isoformat(),
            updated_at=a.updated_at.isoformat(),
        )
        for a in artifacts
    ]

    return ArtifactListResponse(artifacts=summaries, total=len(summaries))


@router.get("/{artifact_id}")
async def get_artifact(
    artifact_id: str,
    tenant_id: str,
    version: Optional[int] = Query(None),
) -> Artifact:
    """Get an artifact by ID."""
    artifact = await artifact_store.get_by_id(
        artifact_id=artifact_id,
        tenant_id=tenant_id,
        version=version,
    )

    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    return artifact


@router.get("/{artifact_id}/versions", response_model=ArtifactVersionsResponse)
async def list_artifact_versions(
    artifact_id: str,
    tenant_id: str,
) -> ArtifactVersionsResponse:
    """List all versions of an artifact."""
    versions = await artifact_store.list_versions(
        artifact_id=artifact_id,
        tenant_id=tenant_id,
    )

    return ArtifactVersionsResponse(
        artifact_id=artifact_id,
        versions=versions,
    )


@router.delete("/{artifact_id}")
async def delete_artifact(
    artifact_id: str,
    tenant_id: str,
) -> dict:
    """Delete an artifact and all its versions."""
    deleted = await artifact_store.delete(
        artifact_id=artifact_id,
        tenant_id=tenant_id,
    )

    if not deleted:
        raise HTTPException(status_code=404, detail="Artifact not found")

    return {"deleted": True, "artifact_id": artifact_id}


@router.get("/{artifact_id}/export")
async def export_artifact(
    artifact_id: str,
    tenant_id: str,
    format: str = Query("markdown", enum=["markdown", "json"]),
):
    """Export an artifact in the specified format."""
    artifact = await artifact_store.get_by_id(
        artifact_id=artifact_id,
        tenant_id=tenant_id,
    )

    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    if format == "markdown":
        return {
            "content": artifact.content_markdown,
            "filename": f"{artifact.metadata.title.replace(' ', '_')}.md",
            "content_type": "text/markdown",
        }
    else:
        return artifact.model_dump()
```

---

### Task 2.7: Update Main Routes to Include Artifacts

**apps/agent_api/src/agent_api/main.py** (update)
```python
# Add to imports
from agent_api.api.artifacts import router as artifacts_router

# Add after other router includes
app.include_router(artifacts_router)
```

---

### Task 2.8: Update Graph to Support Generation

Update **packages/agent_core/src/agent_core/graph/base_graph.py**:

```python
"""Main LangGraph agent graph with content generation."""

from langgraph.graph import StateGraph, END

from agent_core.state.models import AgentState, IntentType
from agent_core.graph.nodes.ingest_context import ingest_context
from agent_core.graph.nodes.route_intent import route_intent
from agent_core.graph.nodes.gather_context import gather_context
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
    Create the main agent graph with content generation.

    Flow:
    ingest_context -> route_intent -> gather_context
                                           |
                                     [conditional]
                                     /          \
                            generate_content    draft_or_answer
                                     \          /
                                      finalize -> END
    """
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("ingest_context", ingest_context)
    graph.add_node("route_intent", route_intent)
    graph.add_node("gather_context", gather_context)
    graph.add_node("draft_or_answer", draft_or_answer)
    graph.add_node("generate_content", generate_content)
    graph.add_node("finalize", finalize)

    # Add edges
    graph.set_entry_point("ingest_context")
    graph.add_edge("ingest_context", "route_intent")
    graph.add_edge("route_intent", "gather_context")

    # Conditional routing after gather_context
    graph.add_conditional_edges(
        "gather_context",
        route_after_gather,
        {
            "generate_content": "generate_content",
            "draft_or_answer": "draft_or_answer",
        },
    )

    graph.add_edge("generate_content", "finalize")
    graph.add_edge("draft_or_answer", "finalize")
    graph.add_edge("finalize", END)

    return graph


def compile_agent_graph(checkpointer=None):
    """Compile the graph with optional checkpointer."""
    graph = create_agent_graph()
    return graph.compile(checkpointer=checkpointer)
```

---

## Azure Configuration Checklist

### 1. Verify Artifacts Container

Ensure the `artifacts` container exists with the correct configuration:

```bash
az cosmosdb sql container show \
  --account-name <your-cosmos-account> \
  --resource-group <your-rg> \
  --database-name invictus-copilot \
  --name artifacts
```

If not exists, create it:

```bash
az cosmosdb sql container create \
  --account-name <your-cosmos-account> \
  --resource-group <your-rg> \
  --database-name invictus-copilot \
  --name artifacts \
  --partition-key-path /tenant_id \
  --throughput 400
```

### 2. (Optional) Set Up Blob Storage

For large artifacts, you may want to store them in Blob Storage:

```bash
# Create storage account (if not exists)
az storage account create \
  --name <storage-account-name> \
  --resource-group <your-rg> \
  --location <location> \
  --sku Standard_LRS

# Create container for artifacts
az storage container create \
  --account-name <storage-account-name> \
  --name artifacts \
  --auth-mode login
```

---

## Testing Checklist

### Unit Tests

- [ ] `test_artifact_models.py` - Artifact schema validation
- [ ] `test_artifact_store.py` - Cosmos DB storage operations
- [ ] `test_report_generation.py` - Report generation subgraph
- [ ] `test_edit_artifact.py` - Edit artifact subgraph

### Integration Tests

- [ ] Generate a memo from context
- [ ] Generate an investment report
- [ ] Edit a specific section
- [ ] Edit full document
- [ ] List artifacts by tenant
- [ ] Get artifact versions
- [ ] Export artifact as markdown

### Manual Testing

```bash
# Generate a memo
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Generate an investment memo for this opportunity",
    "tenant_id": "test-tenant",
    "user_id": "test-user",
    "page_context": {
      "module_id": "deals",
      "screen_name": "opportunity_detail",
      "entity_type": "opportunity",
      "entity_id": "opp-123"
    }
  }'

# List artifacts
curl "http://localhost:8000/v1/artifacts?tenant_id=test-tenant"

# Get artifact
curl "http://localhost:8000/v1/artifacts/{artifact_id}?tenant_id=test-tenant"

# Get artifact versions
curl "http://localhost:8000/v1/artifacts/{artifact_id}/versions?tenant_id=test-tenant"

# Edit artifact via chat
curl -X POST http://localhost:8000/v1/copilot/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Revise section 2 with a more formal tone",
    "tenant_id": "test-tenant",
    "user_id": "test-user",
    "session_id": "<same-session-id>"
  }'
```

---

## Expected Deliverables

After completing Phase 2:

1. **Artifact Storage System**:
   - Artifact model with sections, citations, versioning
   - Cosmos DB storage with version history
   - List, get, delete, export operations

2. **Report Generation Subgraph**:
   - Outline planning
   - Section-by-section generation
   - Citation tracking
   - Markdown output

3. **Edit Artifact Subgraph**:
   - Section-level editing
   - Full document editing
   - Version creation on edit

4. **API Endpoints**:
   - `GET /v1/artifacts` - List artifacts
   - `GET /v1/artifacts/{id}` - Get artifact
   - `GET /v1/artifacts/{id}/versions` - Get versions
   - `DELETE /v1/artifacts/{id}` - Delete artifact
   - `GET /v1/artifacts/{id}/export` - Export artifact

5. **Working demo**:
   - "Generate Investment Memo for this opportunity"
   - "Revise section 2 with a more formal tone"
   - View and manage generated artifacts

---

## Next Phase

Once Phase 2 is complete and tested, proceed to [Phase 3: HITL & Governance](phase-3-hitl-governance.md).
