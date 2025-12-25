"""Deals MCP tools with mock data for development.

This module provides placeholder implementations of Deals-related MCP tools.
In production, these would connect to actual Cosmos DB and other services.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from common.logging import get_logger

logger = get_logger(__name__)


# ============================================================
# Mock Data Store
# ============================================================

MOCK_OPPORTUNITIES = {
    "opp-001": {
        "opportunity_id": "opp-001",
        "name": "Acme Corp Private Equity Fund III",
        "status": "active",
        "type": "private_equity",
        "target_raise": 500000000,
        "current_committed": 350000000,
        "close_date": "2025-03-31",
        "manager": "BlackStone Partners",
        "vintage_year": 2025,
        "sector": "Technology",
        "geography": "North America",
        "minimum_investment": 5000000,
        "management_fee": "2%",
        "carry": "20%",
        "description": "A growth equity fund focusing on mid-market technology companies.",
        "stage": "Due Diligence",
        "risk_rating": "Medium",
        "created_at": "2024-11-01T00:00:00Z",
        "updated_at": "2024-12-20T00:00:00Z",
    },
    "opp-002": {
        "opportunity_id": "opp-002",
        "name": "Green Energy Infrastructure Fund II",
        "status": "active",
        "type": "infrastructure",
        "target_raise": 750000000,
        "current_committed": 500000000,
        "close_date": "2025-06-30",
        "manager": "Sustainable Capital Partners",
        "vintage_year": 2025,
        "sector": "Energy",
        "geography": "Global",
        "minimum_investment": 10000000,
        "management_fee": "1.5%",
        "carry": "15%",
        "description": "Infrastructure fund focusing on renewable energy projects worldwide.",
        "stage": "Investment Committee Review",
        "risk_rating": "Low",
        "created_at": "2024-10-15T00:00:00Z",
        "updated_at": "2024-12-18T00:00:00Z",
    },
    "opp-003": {
        "opportunity_id": "opp-003",
        "name": "Healthcare Ventures Fund V",
        "status": "pending",
        "type": "venture_capital",
        "target_raise": 300000000,
        "current_committed": 75000000,
        "close_date": "2025-09-30",
        "manager": "MedTech Ventures",
        "vintage_year": 2025,
        "sector": "Healthcare",
        "geography": "United States",
        "minimum_investment": 2000000,
        "management_fee": "2.5%",
        "carry": "25%",
        "description": "Early-stage venture fund targeting healthcare innovation.",
        "stage": "Prescreening",
        "risk_rating": "High",
        "created_at": "2024-12-01T00:00:00Z",
        "updated_at": "2024-12-22T00:00:00Z",
    },
}

MOCK_PRESCREENING_REPORTS = {
    "opp-001": {
        "opportunity_id": "opp-001",
        "report_date": "2024-12-15",
        "analyst": "John Smith",
        "recommendation": "proceed",
        "risk_rating": "medium",
        "executive_summary": (
            "Acme Corp PE Fund III represents a compelling investment opportunity "
            "in the mid-market technology space. The fund manager has a strong track "
            "record with consistent returns across previous vintages."
        ),
        "key_findings": [
            "Strong management team with 20+ years combined experience",
            "Track record shows consistent 18% net IRR across Fund I and II",
            "Technology sector exposure provides growth potential",
            "Portfolio diversification across 15+ companies reduces concentration risk",
            "Clear value creation playbook with operational improvement focus",
        ],
        "concerns": [
            "High valuation multiples in current market environment",
            "Currency exposure to EUR (30% of target portfolio)",
            "Key person risk with founding partners",
        ],
        "investment_thesis": (
            "The fund targets mid-market technology companies with EBITDA between "
            "$10-50M, focusing on software and tech-enabled services. The manager's "
            "operational approach has historically driven 2-3x multiple expansion."
        ),
        "financial_highlights": {
            "target_irr": "18-22%",
            "target_moic": "2.5x",
            "fund_size": "$500M",
            "investment_period": "5 years",
            "fund_life": "10 years",
        },
        "conclusion": (
            "Recommend proceeding to full due diligence based on strong fundamentals, "
            "experienced team, and attractive risk-adjusted return profile."
        ),
    },
    "opp-002": {
        "opportunity_id": "opp-002",
        "report_date": "2024-12-10",
        "analyst": "Sarah Johnson",
        "recommendation": "proceed",
        "risk_rating": "low",
        "executive_summary": (
            "Green Energy Infrastructure Fund II offers exposure to high-quality "
            "renewable energy assets with stable, long-term cash flows backed by "
            "government contracts and PPAs."
        ),
        "key_findings": [
            "Portfolio of operating wind and solar assets with 15+ year PPAs",
            "Strong ESG alignment for investor mandates",
            "Experienced manager with $5B+ in renewable energy AUM",
            "Conservative leverage profile (40% LTV)",
            "Diversified across 8 countries and 3 technologies",
        ],
        "concerns": [
            "Regulatory risk in certain jurisdictions",
            "Technology obsolescence risk for older assets",
            "Interest rate sensitivity on returns",
        ],
        "investment_thesis": (
            "The fund provides stable, yield-oriented returns from operating renewable "
            "energy infrastructure. Long-term contracted revenues provide visibility "
            "while expansion optionality offers upside."
        ),
        "financial_highlights": {
            "target_irr": "10-12%",
            "target_moic": "1.8x",
            "fund_size": "$750M",
            "cash_yield": "6-7%",
            "fund_life": "12 years",
        },
        "conclusion": (
            "Recommend proceeding to full due diligence. Strong fit for investors "
            "seeking stable, ESG-aligned infrastructure exposure."
        ),
    },
}

MOCK_INVESTMENT_MEMOS = {
    "opp-001": {
        "opportunity_id": "opp-001",
        "memo_date": "2024-12-20",
        "version": "1.0",
        "author": "Investment Committee",
        "status": "draft",
        "sections": {
            "executive_summary": (
                "This investment memo recommends a $25M commitment to Acme Corp "
                "Private Equity Fund III, representing 5% of the target fund size. "
                "The investment aligns with our technology allocation strategy and "
                "offers attractive risk-adjusted returns."
            ),
            "investment_thesis": (
                "Acme Corp PE Fund III targets mid-market technology companies with "
                "proven business models and opportunities for operational improvement. "
                "The manager's track record demonstrates consistent value creation "
                "through a combination of revenue growth and margin expansion."
            ),
            "manager_assessment": (
                "The fund manager has delivered strong performance across two prior "
                "vintages, with Fund I generating 2.8x MOIC and Fund II tracking at "
                "1.9x MOIC (2021 vintage). The team has deep sector expertise and "
                "a repeatable value creation playbook."
            ),
            "risk_analysis": (
                "Key risks include: (1) High entry valuations in technology sector, "
                "(2) Potential economic slowdown impacting portfolio companies, "
                "(3) Key person dependency on founding partners. Mitigants include "
                "diversification, conservative leverage, and succession planning."
            ),
            "terms_analysis": (
                "Terms are market-standard: 2% management fee, 20% carry with 8% "
                "preferred return. The fund offers co-investment rights and LPAC seat "
                "for commitments above $20M."
            ),
            "recommendation": (
                "The Investment Committee recommends approval of a $25M commitment "
                "to Acme Corp PE Fund III, subject to completion of legal due diligence "
                "and reference checks."
            ),
        },
    },
    "opp-002": {
        "opportunity_id": "opp-002",
        "memo_date": "2024-12-18",
        "version": "1.0",
        "author": "Investment Committee",
        "status": "final",
        "sections": {
            "executive_summary": (
                "This investment memo recommends a $40M commitment to Green Energy "
                "Infrastructure Fund II, supporting our sustainable investment mandate "
                "and infrastructure allocation targets."
            ),
            "investment_thesis": (
                "The fund provides exposure to operating renewable energy assets with "
                "long-term contracted revenues. The yield-oriented strategy complements "
                "our existing growth-focused infrastructure portfolio."
            ),
            "manager_assessment": (
                "Sustainable Capital Partners is a leading renewable energy investor "
                "with $5B+ AUM and a 15-year track record. Fund I generated 1.7x MOIC "
                "with 9% net IRR, meeting investor expectations."
            ),
            "risk_analysis": (
                "Primary risks include regulatory changes affecting renewable subsidies, "
                "technology evolution, and currency exposure. The manager mitigates "
                "through geographic diversification and hedging strategies."
            ),
            "terms_analysis": (
                "Attractive fee structure: 1.5% management fee, 15% carry with 7% "
                "preferred return. Strong alignment with GP committing 5% of fund."
            ),
            "recommendation": (
                "The Investment Committee recommends approval of a $40M commitment "
                "to Green Energy Infrastructure Fund II."
            ),
        },
    },
}

MOCK_ACTIVITY_TIMELINE = {
    "opp-001": [
        {
            "activity_id": "act-001",
            "date": "2024-12-20T14:30:00Z",
            "action": "Investment memo draft created",
            "user": "pm@firm.com",
            "type": "document",
            "details": {"document_type": "investment_memo", "version": "1.0"},
        },
        {
            "activity_id": "act-002",
            "date": "2024-12-18T10:00:00Z",
            "action": "Due diligence meeting scheduled",
            "user": "analyst@firm.com",
            "type": "meeting",
            "details": {"meeting_date": "2025-01-10", "attendees": ["Fund Manager", "IC"]},
        },
        {
            "activity_id": "act-003",
            "date": "2024-12-15T16:45:00Z",
            "action": "Prescreening completed - Proceed",
            "user": "analyst@firm.com",
            "type": "status_change",
            "details": {"old_status": "Prescreening", "new_status": "Due Diligence"},
        },
        {
            "activity_id": "act-004",
            "date": "2024-12-10T09:15:00Z",
            "action": "Prescreening report uploaded",
            "user": "analyst@firm.com",
            "type": "document",
            "details": {"document_type": "prescreening_report"},
        },
        {
            "activity_id": "act-005",
            "date": "2024-12-05T11:30:00Z",
            "action": "Documents received from manager",
            "user": "analyst@firm.com",
            "type": "document",
            "details": {"document_count": 12, "categories": ["PPM", "DDQ", "Financials"]},
        },
        {
            "activity_id": "act-006",
            "date": "2024-11-01T08:00:00Z",
            "action": "Opportunity created",
            "user": "system",
            "type": "system",
            "details": {"source": "Fund Manager Outreach"},
        },
    ],
    "opp-002": [
        {
            "activity_id": "act-101",
            "date": "2024-12-18T16:00:00Z",
            "action": "Investment memo finalized",
            "user": "ic@firm.com",
            "type": "document",
            "details": {"document_type": "investment_memo", "version": "1.0"},
        },
        {
            "activity_id": "act-102",
            "date": "2024-12-15T14:00:00Z",
            "action": "Investment Committee review scheduled",
            "user": "pm@firm.com",
            "type": "meeting",
            "details": {"meeting_date": "2024-12-20"},
        },
        {
            "activity_id": "act-103",
            "date": "2024-12-10T10:30:00Z",
            "action": "Prescreening completed - Proceed",
            "user": "analyst@firm.com",
            "type": "status_change",
            "details": {"old_status": "Prescreening", "new_status": "IC Review"},
        },
        {
            "activity_id": "act-104",
            "date": "2024-10-15T09:00:00Z",
            "action": "Opportunity created",
            "user": "system",
            "type": "system",
            "details": {"source": "Consultant Referral"},
        },
    ],
}


# ============================================================
# Result Model
# ============================================================


class DealsMCPToolResult(BaseModel):
    """Result from a Deals MCP tool call."""

    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    latency_ms: float = 0


# ============================================================
# Tool Implementations
# ============================================================


async def get_opportunity_details(
    opportunity_id: str,
    tenant_id: str,
    user_id: str | None = None,
) -> DealsMCPToolResult:
    """
    Get detailed information about an opportunity.

    Args:
        opportunity_id: The opportunity identifier
        tenant_id: The tenant identifier
        user_id: Optional user identifier for access control

    Returns:
        DealsMCPToolResult with opportunity metadata
    """
    start_time = datetime.utcnow()

    logger.info(
        "Getting opportunity details",
        opportunity_id=opportunity_id,
        tenant_id=tenant_id,
    )

    # Mock implementation - in production, query Cosmos DB
    if opportunity_id in MOCK_OPPORTUNITIES:
        latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        return DealsMCPToolResult(
            success=True,
            data=MOCK_OPPORTUNITIES[opportunity_id],
            latency_ms=latency_ms,
        )

    latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
    return DealsMCPToolResult(
        success=False,
        error=f"Opportunity not found: {opportunity_id}",
        latency_ms=latency_ms,
    )


async def get_prescreening_report(
    opportunity_id: str,
    tenant_id: str,
    user_id: str | None = None,
    include_sections: list[str] | None = None,
) -> DealsMCPToolResult:
    """
    Get the prescreening report for an opportunity.

    Args:
        opportunity_id: The opportunity identifier
        tenant_id: The tenant identifier
        user_id: Optional user identifier for access control
        include_sections: Optional list of sections to include

    Returns:
        DealsMCPToolResult with prescreening report data
    """
    start_time = datetime.utcnow()

    logger.info(
        "Getting prescreening report",
        opportunity_id=opportunity_id,
        tenant_id=tenant_id,
    )

    if opportunity_id in MOCK_PRESCREENING_REPORTS:
        report = MOCK_PRESCREENING_REPORTS[opportunity_id].copy()

        # Filter sections if specified
        if include_sections:
            filtered_report = {k: v for k, v in report.items() if k in include_sections}
            filtered_report["opportunity_id"] = opportunity_id
            report = filtered_report

        latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        return DealsMCPToolResult(
            success=True,
            data=report,
            latency_ms=latency_ms,
        )

    latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
    return DealsMCPToolResult(
        success=False,
        error=f"No prescreening report found for: {opportunity_id}",
        latency_ms=latency_ms,
    )


async def get_investment_memo(
    opportunity_id: str,
    tenant_id: str,
    user_id: str | None = None,
    version: str | None = None,
    section: str | None = None,
) -> DealsMCPToolResult:
    """
    Get the investment memo for an opportunity.

    Args:
        opportunity_id: The opportunity identifier
        tenant_id: The tenant identifier
        user_id: Optional user identifier for access control
        version: Specific version to retrieve (optional)
        section: Specific section to retrieve (optional)

    Returns:
        DealsMCPToolResult with investment memo data
    """
    start_time = datetime.utcnow()

    logger.info(
        "Getting investment memo",
        opportunity_id=opportunity_id,
        tenant_id=tenant_id,
        version=version,
        section=section,
    )

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
                latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                return DealsMCPToolResult(
                    success=False,
                    error=f"Section '{section}' not found in memo",
                    latency_ms=latency_ms,
                )

        latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        return DealsMCPToolResult(
            success=True,
            data=memo,
            latency_ms=latency_ms,
        )

    latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
    return DealsMCPToolResult(
        success=False,
        error=f"No investment memo found for: {opportunity_id}",
        latency_ms=latency_ms,
    )


async def get_opportunity_activity(
    opportunity_id: str,
    tenant_id: str,
    user_id: str | None = None,
    activity_types: list[str] | None = None,
    limit: int = 20,
    offset: int = 0,
) -> DealsMCPToolResult:
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
        DealsMCPToolResult with activity timeline data
    """
    start_time = datetime.utcnow()

    logger.info(
        "Getting opportunity activity",
        opportunity_id=opportunity_id,
        tenant_id=tenant_id,
        activity_types=activity_types,
        limit=limit,
        offset=offset,
    )

    if opportunity_id in MOCK_ACTIVITY_TIMELINE:
        activities = MOCK_ACTIVITY_TIMELINE[opportunity_id]

        # Filter by type if specified
        if activity_types:
            activities = [a for a in activities if a.get("type") in activity_types]

        # Apply pagination
        total = len(activities)
        activities = activities[offset : offset + limit]

        latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        return DealsMCPToolResult(
            success=True,
            data={
                "opportunity_id": opportunity_id,
                "activities": activities,
                "total": total,
                "limit": limit,
                "offset": offset,
            },
            latency_ms=latency_ms,
        )

    latency_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
    return DealsMCPToolResult(
        success=False,
        error=f"No activity found for: {opportunity_id}",
        latency_ms=latency_ms,
    )


# ============================================================
# Tool Registry
# ============================================================

DEALS_TOOLS = {
    "get_opportunity_details": get_opportunity_details,
    "get_prescreening_report": get_prescreening_report,
    "get_investment_memo": get_investment_memo,
    "get_opportunity_activity": get_opportunity_activity,
}


async def call_deals_tool(
    tool_name: str,
    arguments: dict[str, Any],
) -> DealsMCPToolResult:
    """
    Call a Deals MCP tool by name.

    Args:
        tool_name: Name of the tool to call
        arguments: Arguments to pass to the tool

    Returns:
        DealsMCPToolResult with the tool output
    """
    if tool_name not in DEALS_TOOLS:
        return DealsMCPToolResult(
            success=False,
            error=f"Unknown Deals tool: {tool_name}",
        )

    tool_fn = DEALS_TOOLS[tool_name]
    try:
        return await tool_fn(**arguments)
    except Exception as e:
        logger.error("Deals tool call failed", tool_name=tool_name, error=str(e))
        return DealsMCPToolResult(
            success=False,
            error=f"Tool execution failed: {str(e)}",
        )


def list_available_tools() -> list[str]:
    """List all available Deals MCP tools."""
    return list(DEALS_TOOLS.keys())
