"""Tavily web search tool for internet research."""

from dataclasses import dataclass
from typing import Any

from tavily import AsyncTavilyClient

from common.config import get_settings
from common.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


@dataclass
class WebSearchResult:
    """Result from web search."""

    success: bool
    query: str
    results: list[dict[str, Any]]
    answer: str | None = None
    error: str | None = None


async def web_search(
    query: str,
    search_depth: str = "basic",
    max_results: int = 2,
    include_answer: bool = True,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
) -> WebSearchResult:
    """
    Search the web using Tavily API.

    Args:
        query: The search query
        search_depth: "basic" for fast results, "advanced" for comprehensive
        max_results: Maximum number of results to return (1-10)
        include_answer: Whether to include AI-generated answer summary
        include_domains: List of domains to include in search
        exclude_domains: List of domains to exclude from search

    Returns:
        WebSearchResult with search results and optional answer
    """
    if not settings.tavily_api_key:
        logger.warning("Tavily API key not configured")
        return WebSearchResult(
            success=False,
            query=query,
            results=[],
            error="Tavily API key not configured",
        )

    try:
        client = AsyncTavilyClient(api_key=settings.tavily_api_key)

        # Build search parameters
        search_params = {
            "query": query,
            "search_depth": search_depth,
            "max_results": min(max_results, 10),
            "include_answer": include_answer,
        }

        if include_domains:
            search_params["include_domains"] = include_domains
        if exclude_domains:
            search_params["exclude_domains"] = exclude_domains

        logger.info(
            "Executing web search",
            query=query,
            search_depth=search_depth,
            max_results=max_results,
        )

        response = await client.search(**search_params)

        # Extract results
        results = []
        for result in response.get("results", []):
            results.append({
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "content": result.get("content", ""),
                "score": result.get("score", 0),
            })

        answer = response.get("answer") if include_answer else None

        logger.info(
            "Web search completed",
            query=query,
            result_count=len(results),
            has_answer=bool(answer),
        )

        return WebSearchResult(
            success=True,
            query=query,
            results=results,
            answer=answer,
        )

    except Exception as e:
        logger.error("Web search failed", query=query, error=str(e))
        return WebSearchResult(
            success=False,
            query=query,
            results=[],
            error=str(e),
        )


async def search_for_context(
    user_question: str,
    opportunity_name: str | None = None,
    sector: str | None = None,
) -> WebSearchResult:
    """
    Search for context relevant to a user's question.

    Automatically constructs a search query based on the context.

    Args:
        user_question: The user's question
        opportunity_name: Optional opportunity/company name for context
        sector: Optional sector/industry for context

    Returns:
        WebSearchResult with relevant web results
    """
    # Build contextual query
    query_parts = [user_question]

    if opportunity_name:
        query_parts.append(f'"{opportunity_name}"')
    if sector:
        query_parts.append(sector)

    query = " ".join(query_parts)

    # Exclude unreliable domains for financial research
    exclude_domains = [
        "reddit.com",
        "quora.com",
        "wikipedia.org",  # Exclude for financial accuracy
    ]

    return await web_search(
        query=query,
        search_depth="advanced",
        max_results=2,
        include_answer=True,
        exclude_domains=exclude_domains,
    )
