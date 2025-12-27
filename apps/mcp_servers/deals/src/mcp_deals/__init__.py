"""Deals MCP Server package.

This package provides an MCP server for the Deals/Opportunities domain.
"""

from mcp_deals.server import create_app
from mcp_deals.tools import (
    get_opportunity_details,
    get_prescreening_report,
    get_investment_memo,
    get_opportunity_activity,
)

__version__ = "0.1.0"

__all__ = [
    "create_app",
    "get_opportunity_details",
    "get_prescreening_report",
    "get_investment_memo",
    "get_opportunity_activity",
]
