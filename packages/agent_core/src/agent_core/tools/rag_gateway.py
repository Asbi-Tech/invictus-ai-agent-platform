"""RAG Gateway tool for document field extraction."""

from datetime import datetime
from typing import Any

import httpx
from pydantic import BaseModel, Field

from common.config import get_settings
from common.errors import RAGGatewayError
from common.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


class FieldDefinition(BaseModel):
    """Definition of a field to extract from documents."""

    name: str = Field(description="Name of the field to extract")
    description: str = Field(description="What to look for in the documents")
    instructions: str = Field(description="How to extract the field")
    type: str = Field(default="string", description="Field type: string, number, object, array")
    options: list[str] | None = Field(default=None, description="Allowed values for the field")


class StorageConfig(BaseModel):
    """Azure Blob Storage configuration."""

    account_url: str
    filesystem: str = "documents"
    base_prefix: str


class RetrievalConfig(BaseModel):
    """Configuration for document retrieval."""

    top_k: int = 10
    search_strategy: str = "hybrid"
    over_retrieve_k: int = 50


class TraceInfo(BaseModel):
    """Trace information for request tracking."""

    request_id: str
    user_id: str
    session_id: str


class SourceChunk(BaseModel):
    """A source chunk from RAG extraction."""

    chunk_id: str
    content: str
    doc_id: str
    page_numbers: list[int] = Field(default_factory=list)
    section_path: str | None = None
    bounding_boxes: list[dict[str, Any]] = Field(default_factory=list)


class ExtractedFieldResult(BaseModel):
    """Full result for an extracted field including sources."""

    name: str
    value: Any
    confidence: float | None = None
    reasoning: str | None = None
    sources: list[SourceChunk] = Field(default_factory=list)


class ExtractFieldsRequest(BaseModel):
    """Request payload for the ExtractFields API."""

    tenant_id: str
    doc_ids: list[str]
    fields: list[FieldDefinition]
    retrieval_config: RetrievalConfig = Field(default_factory=RetrievalConfig)
    storage: StorageConfig
    system_instructions: str = (
        "Extract the requested information from the documents. "
        "Return only explicitly stated information. "
        "If information is not found, return null."
    )
    trace: TraceInfo | None = None
    include_bounding_boxes: bool = False


class ExtractedField(BaseModel):
    """A single extracted field result."""

    name: str
    value: Any
    confidence: float | None = None
    source_chunks: list[dict[str, Any]] = Field(default_factory=list)


class ExtractFieldsResponse(BaseModel):
    """Response from the ExtractFields API."""

    fields: dict[str, Any]  # field_name -> extracted_value (for backward compat)
    field_results: list[ExtractedFieldResult] = Field(default_factory=list)  # Full results with sources
    sources: list[dict[str, Any]] = Field(default_factory=list)  # All unique sources (without bounding boxes)
    metadata: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0


async def extract_fields(
    tenant_id: str,
    doc_ids: list[str],
    fields: list[FieldDefinition],
    storage: StorageConfig,
    user_id: str = "",
    session_id: str = "",
    system_instructions: str | None = None,
) -> ExtractFieldsResponse:
    """
    Extract structured fields from documents using the RAG Gateway.

    Args:
        tenant_id: The tenant ID
        doc_ids: List of document IDs to search
        fields: List of field definitions to extract
        storage: Azure Blob Storage configuration
        user_id: User ID for tracing
        session_id: Session ID for tracing
        system_instructions: Optional custom system instructions

    Returns:
        ExtractFieldsResponse with extracted field values

    Raises:
        RAGGatewayError: If the extraction fails
    """
    start_time = datetime.utcnow()

    request = ExtractFieldsRequest(
        tenant_id=tenant_id,
        doc_ids=doc_ids,
        fields=fields,
        storage=storage,
        trace=TraceInfo(
            request_id=f"{session_id}-{datetime.utcnow().timestamp()}",
            user_id=user_id,
            session_id=session_id,
        ),
        include_bounding_boxes=True,
    )

    if system_instructions:
        request.system_instructions = system_instructions

    # Log the request payload for debugging
    logger.info(
        "RAG Gateway request payload",
        tenant_id=tenant_id,
        doc_ids=doc_ids,
        field_names=[f.name for f in fields],
        field_instructions={f.name: f.instructions[:100] + "..." for f in fields},
        storage_prefix=storage.base_prefix,
    )

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            headers = {"Content-Type": "application/json"}
            if settings.rag_gateway_api_key:
                headers["x-functions-key"] = settings.rag_gateway_api_key

            # Build the full URL (Azure Functions use /api/ prefix)
            url = f"{settings.rag_gateway_url}/api/ExtractFields"

            logger.info(
                "Calling RAG Gateway ExtractFields",
                url=url,
                tenant_id=tenant_id,
                doc_count=len(doc_ids),
                field_count=len(fields),
            )

            response = await client.post(
                url,
                json=request.model_dump(exclude_none=True),
                headers=headers,
            )
            response.raise_for_status()

            data = response.json()
            latency = (datetime.utcnow() - start_time).total_seconds() * 1000

            # Log the raw response structure
            logger.info(
                "RAG Gateway raw response",
                response_keys=list(data.keys()),
                has_fields="fields" in data or "results" in data,
            )

            # Parse the response
            raw_fields = data.get("fields", data.get("results", []))

            # Handle both list and dict formats
            field_results: list[ExtractedFieldResult] = []
            all_sources: list[dict[str, Any]] = []
            fields_dict: dict[str, Any] = {}

            if isinstance(raw_fields, list):
                # New format: list of field objects with sources
                seen_chunks: set[str] = set()

                for field in raw_fields:
                    name = field.get("name")
                    value = field.get("value")
                    fields_dict[name] = value

                    # Collect sources from this field
                    field_sources = field.get("sources", [])

                    # Build SourceChunk objects for field_results
                    source_chunks = []
                    for source in field_sources:
                        try:
                            source_chunks.append(SourceChunk(
                                chunk_id=source.get("chunk_id", ""),
                                content=source.get("content", ""),
                                doc_id=source.get("doc_id", ""),
                                page_numbers=source.get("page_numbers", []),
                                section_path=source.get("section_path"),
                                bounding_boxes=source.get("bounding_boxes", []),
                            ))
                        except Exception as e:
                            logger.warning(f"Failed to parse source chunk: {e}")

                    field_results.append(ExtractedFieldResult(
                        name=name,
                        value=value,
                        confidence=field.get("confidence"),
                        reasoning=field.get("reasoning"),
                        sources=source_chunks,
                    ))

                    # Add to all_sources (avoid duplicates by chunk_id)
                    for source in field_sources:
                        chunk_id = source.get("chunk_id", "")
                        if chunk_id and chunk_id not in seen_chunks:
                            clean_source = {
                                "source": "rag",
                                "chunk_id": chunk_id,
                                "content": source.get("content", ""),
                                "doc_id": source.get("doc_id", ""),
                                "page_numbers": source.get("page_numbers", []),
                                "section_path": source.get("section_path"),
                                "bounding_boxes": source.get("bounding_boxes", []),
                            }
                            all_sources.append(clean_source)
                            seen_chunks.add(chunk_id)

                extracted_fields = fields_dict
            else:
                # Old format: dict of {name: value}
                extracted_fields = raw_fields

            # Log extracted field values (truncated for readability)
            logger.info(
                "RAG Gateway extracted fields",
                field_names=list(extracted_fields.keys()),
                field_values={
                    k: (str(v)[:200] + "..." if v and len(str(v)) > 200 else str(v))
                    for k, v in extracted_fields.items()
                },
                source_count=len(all_sources),
            )

            logger.info(
                "RAG extraction completed",
                field_count=len(extracted_fields),
                source_count=len(all_sources),
                latency_ms=latency,
            )

            return ExtractFieldsResponse(
                fields=extracted_fields,
                field_results=field_results,
                sources=all_sources,
                metadata=data.get("metadata", {}),
                latency_ms=latency,
            )

        except httpx.HTTPStatusError as e:
            logger.error(
                "RAG Gateway HTTP error",
                status=e.response.status_code,
                detail=e.response.text[:500] if e.response.text else "",
            )
            raise RAGGatewayError(
                f"RAG Gateway returned {e.response.status_code}",
                status_code=e.response.status_code,
            )
        except httpx.RequestError as e:
            logger.error("RAG Gateway request error", error=str(e))
            raise RAGGatewayError(f"Failed to connect to RAG Gateway: {e}")
        except Exception as e:
            logger.error("RAG Gateway error", error=str(e))
            raise RAGGatewayError(f"Failed to extract fields: {e}")


def generate_fields_for_question(question: str) -> list[FieldDefinition]:
    """
    Generate field definitions based on a user question.

    This is a simple heuristic approach. For production, consider using
    an LLM to generate more sophisticated field definitions.

    Args:
        question: The user's question

    Returns:
        List of FieldDefinition objects
    """
    # Default field to answer the question directly
    return [
        FieldDefinition(
            name="answer",
            description=f"Information that answers: {question}",
            instructions=(
                f"Find and extract information from the documents that directly answers "
                f"the following question: {question}. "
                "Include all relevant details, facts, and context. "
                "If the information is not found, return null."
            ),
            type="string",
        ),
        FieldDefinition(
            name="supporting_details",
            description="Additional context and supporting information",
            instructions=(
                "Extract any additional context, numbers, dates, or details that "
                "support or relate to the main answer. Return as a list of key points."
            ),
            type="string",
        ),
    ]
