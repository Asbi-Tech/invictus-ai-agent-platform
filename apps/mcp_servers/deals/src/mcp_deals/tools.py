"""Tool implementations for Deals MCP server.

These are the actual MCP tool functions that will be registered with FastMCP.
In production, these would query Cosmos DB instead of using mock data.
"""

from typing import Any

from mcp_deals.data.mock_data import (
    MOCK_OPPORTUNITIES,
    MOCK_PRESCREENING_REPORTS,
    MOCK_INVESTMENT_MEMOS,
    MOCK_ACTIVITY_TIMELINE,
)


async def get_opportunity_details(
    opportunity_id: str,
    tenant_id: str,
    user_id: str | None = None,
) -> dict[str, Any]:
    """
    Get detailed information about an opportunity.

    Args:
        opportunity_id: The opportunity identifier
        tenant_id: The tenant identifier
        user_id: Optional user identifier for access control

    Returns:
        Dictionary with success status and opportunity data or error
    """
    # In production, validate tenant access here
    # validate_tenant_access(tenant_id)

    if opportunity_id in MOCK_OPPORTUNITIES:
        return {
            "success": True,
            "data": MOCK_OPPORTUNITIES[opportunity_id],
        }

    return {
        "success": False,
        "error": f"Opportunity not found: {opportunity_id}",
    }


async def get_prescreening_report(
    opportunity_id: str,
    tenant_id: str,
    user_id: str | None = None,
    include_sections: list[str] | None = None,
) -> dict[str, Any]:
    """
    Get the prescreening report for an opportunity.

    Args:
        opportunity_id: The opportunity identifier
        tenant_id: The tenant identifier
        user_id: Optional user identifier for access control
        include_sections: Optional list of sections to include

    Returns:
        Dictionary with success status and prescreening report data or error
    """
    if opportunity_id in MOCK_PRESCREENING_REPORTS:
        report = MOCK_PRESCREENING_REPORTS[opportunity_id].copy()

        # Filter sections if specified
        if include_sections:
            filtered_report = {k: v for k, v in report.items() if k in include_sections}
            filtered_report["opportunity_id"] = opportunity_id
            report = filtered_report

        return {
            "success": True,
            "data": report,
        }

    return {
        "success": False,
        "error": f"No prescreening report found for: {opportunity_id}",
    }


async def get_investment_memo(
    opportunity_id: str,
    tenant_id: str,
    user_id: str | None = None,
    version: str | None = None,
    section: str | None = None,
) -> dict[str, Any]:
    """
    Get the investment memo for an opportunity.

    Args:
        opportunity_id: The opportunity identifier
        tenant_id: The tenant identifier
        user_id: Optional user identifier for access control
        version: Specific version to retrieve (optional)
        section: Specific section to retrieve (optional)

    Returns:
        Dictionary with success status and investment memo data or error
    """
    if opportunity_id in MOCK_INVESTMENT_MEMOS:
        memo = MOCK_INVESTMENT_MEMOS[opportunity_id].copy()

        # Return specific section if requested
        if section and "sections" in memo:
            if section in memo["sections"]:
                memo = {
                    "opportunity_id": opportunity_id,
                    "section": section,
                    "content": memo["sections"][section],
                }
            else:
                return {
                    "success": False,
                    "error": f"Section '{section}' not found in memo",
                }

        return {
            "success": True,
            "data": memo,
        }

    return {
        "success": False,
        "error": f"No investment memo found for: {opportunity_id}",
    }


async def get_opportunity_activity(
    opportunity_id: str,
    tenant_id: str,
    user_id: str | None = None,
    activity_types: list[str] | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """
    Get the activity timeline for an opportunity.

    Args:
        opportunity_id: The opportunity identifier
        tenant_id: The tenant identifier
        user_id: Optional user identifier for access control
        activity_types: Filter by activity types (document, meeting, status_change, system)
        limit: Maximum number of activities to return
        offset: Number of activities to skip

    Returns:
        Dictionary with success status and activity timeline data or error
    """
    if opportunity_id in MOCK_ACTIVITY_TIMELINE:
        activities = MOCK_ACTIVITY_TIMELINE[opportunity_id].copy()

        # Filter by type if specified
        if activity_types:
            activities = [a for a in activities if a.get("type") in activity_types]

        # Apply pagination
        total = len(activities)
        activities = activities[offset : offset + limit]

        return {
            "success": True,
            "data": {
                "opportunity_id": opportunity_id,
                "activities": activities,
                "total": total,
                "limit": limit,
                "offset": offset,
            },
        }

    return {
        "success": False,
        "error": f"No activity found for: {opportunity_id}",
    }
