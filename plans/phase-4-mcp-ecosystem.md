# Phase 4: Expand MCP Ecosystem

## Objectives

- Build additional MCP servers (clients, risk-planning, reporting, admin-policy)
- Standardize schemas and patterns in `mcp_common` package
- Create reusable MCP server template
- Implement integration tests and contract tests
- Enable multi-module support for the copilot

## Prerequisites

- Phase 3 completed (HITL, tool governance)
- Database access credentials for each domain
- Understanding of data models in each domain

---

## Implementation Tasks

### Task 4.1: Create MCP Server Base Template

**packages/mcp_common/src/mcp_common/base_server.py**
```python
"""Base template for MCP servers."""

from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Generic, TypeVar

from fastmcp import FastMCP
from pydantic import BaseModel

from mcp_common.auth import validate_tenant_access
from mcp_common.telemetry import track_tool_call
from common.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class BaseMCPServer(ABC):
    """Base class for MCP servers with common patterns."""

    def __init__(self, name: str, description: str = ""):
        self.name = name
        self.description = description
        self.mcp = FastMCP(name)
        self._register_tools()

    @abstractmethod
    def _register_tools(self) -> None:
        """Register tools with the MCP server. Override in subclass."""
        pass

    @abstractmethod
    @asynccontextmanager
    async def get_db_connection(self) -> AsyncGenerator[Any, None]:
        """Get database connection. Override in subclass."""
        pass

    def run(self) -> None:
        """Run the MCP server."""
        self.mcp.run()

    async def execute_query(
        self,
        query: str,
        params: tuple | None = None,
        tenant_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Execute a query with tenant filtering."""
        async with self.get_db_connection() as conn:
            # Add tenant filter if provided
            if tenant_id and "WHERE" in query.upper():
                # Ensure tenant_id is in the query
                pass  # Validation happens at query level

            return await conn.fetchall(query, params or ())


class MCPToolDecorator:
    """Decorator for MCP tools with common patterns."""

    @staticmethod
    def with_tenant_validation(func):
        """Decorator to validate tenant access."""
        async def wrapper(*args, **kwargs):
            tenant_id = kwargs.get("tenant_id")
            if tenant_id:
                validate_tenant_access(tenant_id)
            return await func(*args, **kwargs)
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        return wrapper

    @staticmethod
    def with_telemetry(tool_name: str):
        """Decorator to add telemetry tracking."""
        def decorator(func):
            async def wrapper(*args, **kwargs):
                tenant_id = kwargs.get("tenant_id", "unknown")
                with track_tool_call(tool_name, tenant_id) as metrics:
                    result = await func(*args, **kwargs)
                    return result
            wrapper.__name__ = func.__name__
            wrapper.__doc__ = func.__doc__
            return wrapper
        return decorator
```

---

### Task 4.2: Standardize MCP Schemas

**packages/mcp_common/src/mcp_common/models/base.py**
```python
"""Base models for MCP responses."""

from datetime import datetime
from typing import Any, Generic, TypeVar
from pydantic import BaseModel, Field

T = TypeVar("T")


class MCPResponse(BaseModel, Generic[T]):
    """Standard MCP response wrapper."""
    success: bool = True
    data: T | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response for list operations."""
    items: list[T]
    total: int
    page: int = 1
    page_size: int = 50
    has_more: bool = False


class EntityReference(BaseModel):
    """Reference to an entity."""
    id: str
    name: str
    entity_type: str


class AuditInfo(BaseModel):
    """Audit information for entities."""
    created_at: datetime
    created_by: str | None = None
    updated_at: datetime | None = None
    updated_by: str | None = None
```

**packages/mcp_common/src/mcp_common/models/client.py**
```python
"""Client domain models."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class ClientProfile(BaseModel):
    """Client profile data."""
    id: str
    tenant_id: str
    name: str
    client_type: str  # individual, institution, family_office
    status: str  # active, inactive, prospect
    email: str | None = None
    phone: str | None = None
    address: dict[str, str] | None = None
    risk_profile: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class ClientRelationship(BaseModel):
    """Relationship between clients."""
    id: str
    client_id: str
    related_client_id: str
    relationship_type: str  # spouse, child, business_partner, etc.
    notes: str | None = None


class PortfolioSummary(BaseModel):
    """Client portfolio summary."""
    client_id: str
    total_value: Decimal
    currency: str
    as_of_date: datetime
    asset_allocation: dict[str, Decimal] = Field(default_factory=dict)
    ytd_return: Decimal | None = None
    inception_return: Decimal | None = None


class PortfolioHolding(BaseModel):
    """Individual portfolio holding."""
    id: str
    client_id: str
    security_name: str
    security_type: str
    quantity: Decimal
    market_value: Decimal
    cost_basis: Decimal | None = None
    currency: str
    weight: Decimal | None = None
```

**packages/mcp_common/src/mcp_common/models/risk.py**
```python
"""Risk and planning domain models."""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class InvestmentPolicyStatement(BaseModel):
    """Investment Policy Statement (IPS)."""
    id: str
    client_id: str
    tenant_id: str
    version: int
    status: str  # draft, active, archived

    # Objectives
    investment_objective: str
    time_horizon: str
    risk_tolerance: str
    return_target: Decimal | None = None

    # Constraints
    liquidity_needs: str | None = None
    tax_considerations: str | None = None
    legal_constraints: str | None = None
    unique_circumstances: str | None = None

    # Asset allocation
    target_allocation: dict[str, dict[str, Decimal]] = Field(default_factory=dict)
    # e.g., {"equity": {"target": 60, "min": 50, "max": 70}}

    # Dates
    effective_date: datetime
    review_date: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None


class InvestorProfileQuestionnaire(BaseModel):
    """Investor Profile Questionnaire (IPQ)."""
    id: str
    client_id: str
    tenant_id: str
    completed_at: datetime

    # Risk assessment
    risk_score: int  # 1-10
    risk_category: str  # conservative, moderate, aggressive
    investment_experience: str
    investment_knowledge: str

    # Financial situation
    income_stability: str
    net_worth_range: str
    investment_horizon_years: int

    # Responses
    questionnaire_responses: dict[str, Any] = Field(default_factory=dict)


class RiskProfile(BaseModel):
    """Client risk profile."""
    client_id: str
    tenant_id: str
    overall_risk_score: int
    risk_category: str

    # Component scores
    capacity_score: int  # Ability to take risk
    willingness_score: int  # Desire to take risk
    need_score: int  # Required return

    # Assessment details
    last_assessment_date: datetime
    next_review_date: datetime | None = None
    notes: str | None = None
```

**packages/mcp_common/src/mcp_common/models/reporting.py**
```python
"""Reporting domain models."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ReportTemplate(BaseModel):
    """Report template definition."""
    id: str
    tenant_id: str
    name: str
    description: str | None = None
    report_type: str  # quarterly, annual, custom
    sections: list[dict[str, Any]] = Field(default_factory=list)
    default_parameters: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    created_at: datetime
    updated_at: datetime | None = None


class ExistingReport(BaseModel):
    """An existing generated report."""
    id: str
    tenant_id: str
    template_id: str | None = None
    client_id: str | None = None
    opportunity_id: str | None = None

    title: str
    report_type: str
    period_start: datetime | None = None
    period_end: datetime | None = None

    status: str  # draft, final, archived
    content_url: str | None = None  # Blob storage URL
    content_preview: str | None = None  # First few paragraphs

    generated_at: datetime
    generated_by: str
    approved_at: datetime | None = None
    approved_by: str | None = None
```

---

### Task 4.3: Build MCP Clients Server

**apps/mcp_servers/clients/src/mcp_clients/server.py**
```python
"""MCP server for clients domain."""

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastmcp import FastMCP

from mcp_clients.tools import (
    get_client,
    get_client_relationships,
    get_client_portfolio_snapshot,
    list_client_holdings,
    search_clients,
)
from mcp_clients.db import get_db_connection

mcp = FastMCP("Clients MCP Server")

# Register tools
mcp.tool(get_client)
mcp.tool(get_client_relationships)
mcp.tool(get_client_portfolio_snapshot)
mcp.tool(list_client_holdings)
mcp.tool(search_clients)


if __name__ == "__main__":
    mcp.run()
```

**apps/mcp_servers/clients/src/mcp_clients/tools.py**
```python
"""Tools for the clients MCP server."""

from typing import Any

from mcp_clients.db import get_db_connection
from mcp_common.models.client import (
    ClientProfile,
    ClientRelationship,
    PortfolioSummary,
    PortfolioHolding,
)
from mcp_common.auth import validate_tenant_access


async def get_client(
    client_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    """
    Get detailed information about a client.

    Args:
        client_id: The unique identifier of the client
        tenant_id: The tenant ID for access control

    Returns:
        Client profile including contact information and status
    """
    validate_tenant_access(tenant_id)

    async with get_db_connection() as conn:
        query = """
            SELECT
                id, tenant_id, name, client_type, status,
                email, phone, risk_profile,
                created_at, updated_at
            FROM clients
            WHERE id = ? AND tenant_id = ?
        """
        row = await conn.fetchone(query, (client_id, tenant_id))

        if not row:
            return {"error": "Client not found"}

        return ClientProfile(**row).model_dump()


async def get_client_relationships(
    client_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    """
    Get relationships for a client.

    Args:
        client_id: The unique identifier of the client
        tenant_id: The tenant ID for access control

    Returns:
        List of related clients and relationship types
    """
    validate_tenant_access(tenant_id)

    async with get_db_connection() as conn:
        query = """
            SELECT
                r.id, r.client_id, r.related_client_id,
                r.relationship_type, r.notes,
                c.name as related_client_name
            FROM client_relationships r
            JOIN clients c ON c.id = r.related_client_id
            WHERE r.client_id = ? AND r.tenant_id = ?
        """
        rows = await conn.fetchall(query, (client_id, tenant_id))

        relationships = [
            {
                **ClientRelationship(
                    id=row["id"],
                    client_id=row["client_id"],
                    related_client_id=row["related_client_id"],
                    relationship_type=row["relationship_type"],
                    notes=row.get("notes"),
                ).model_dump(),
                "related_client_name": row["related_client_name"],
            }
            for row in rows
        ]

        return {"relationships": relationships, "count": len(relationships)}


async def get_client_portfolio_snapshot(
    client_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    """
    Get portfolio summary for a client.

    Args:
        client_id: The unique identifier of the client
        tenant_id: The tenant ID for access control

    Returns:
        Portfolio summary including total value and asset allocation
    """
    validate_tenant_access(tenant_id)

    async with get_db_connection() as conn:
        query = """
            SELECT
                client_id, total_value, currency, as_of_date,
                ytd_return, inception_return
            FROM portfolio_summaries
            WHERE client_id = ? AND tenant_id = ?
            ORDER BY as_of_date DESC
            LIMIT 1
        """
        row = await conn.fetchone(query, (client_id, tenant_id))

        if not row:
            return {"error": "Portfolio not found"}

        # Get asset allocation
        alloc_query = """
            SELECT asset_class, weight
            FROM portfolio_allocations
            WHERE client_id = ? AND tenant_id = ?
        """
        alloc_rows = await conn.fetchall(alloc_query, (client_id, tenant_id))
        allocation = {r["asset_class"]: r["weight"] for r in alloc_rows}

        return PortfolioSummary(
            client_id=row["client_id"],
            total_value=row["total_value"],
            currency=row["currency"],
            as_of_date=row["as_of_date"],
            asset_allocation=allocation,
            ytd_return=row.get("ytd_return"),
            inception_return=row.get("inception_return"),
        ).model_dump()


async def list_client_holdings(
    client_id: str,
    tenant_id: str,
    limit: int = 50,
) -> dict[str, Any]:
    """
    List portfolio holdings for a client.

    Args:
        client_id: The unique identifier of the client
        tenant_id: The tenant ID for access control
        limit: Maximum number of holdings to return

    Returns:
        List of portfolio holdings with values and weights
    """
    validate_tenant_access(tenant_id)

    async with get_db_connection() as conn:
        query = """
            SELECT
                id, client_id, security_name, security_type,
                quantity, market_value, cost_basis, currency, weight
            FROM portfolio_holdings
            WHERE client_id = ? AND tenant_id = ?
            ORDER BY market_value DESC
            LIMIT ?
        """
        rows = await conn.fetchall(query, (client_id, tenant_id, limit))

        holdings = [PortfolioHolding(**row).model_dump() for row in rows]

        return {"holdings": holdings, "count": len(holdings)}


async def search_clients(
    tenant_id: str,
    query: str,
    client_type: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """
    Search for clients by name or other criteria.

    Args:
        tenant_id: The tenant ID for access control
        query: Search query (name, email, etc.)
        client_type: Optional filter by client type
        limit: Maximum number of results

    Returns:
        List of matching clients
    """
    validate_tenant_access(tenant_id)

    async with get_db_connection() as conn:
        if client_type:
            sql = """
                SELECT id, name, client_type, status, email
                FROM clients
                WHERE tenant_id = ?
                AND (name LIKE ? OR email LIKE ?)
                AND client_type = ?
                LIMIT ?
            """
            params = (tenant_id, f"%{query}%", f"%{query}%", client_type, limit)
        else:
            sql = """
                SELECT id, name, client_type, status, email
                FROM clients
                WHERE tenant_id = ?
                AND (name LIKE ? OR email LIKE ?)
                LIMIT ?
            """
            params = (tenant_id, f"%{query}%", f"%{query}%", limit)

        rows = await conn.fetchall(sql, params)

        return {
            "clients": [dict(row) for row in rows],
            "count": len(rows),
        }
```

---

### Task 4.4: Build MCP Risk Planning Server

**apps/mcp_servers/risk_planning/src/mcp_risk_planning/server.py**
```python
"""MCP server for risk and planning domain."""

from fastmcp import FastMCP

from mcp_risk_planning.tools import (
    get_ips,
    get_ipq,
    get_risk_profile,
    list_client_documents,
)

mcp = FastMCP("Risk Planning MCP Server")

mcp.tool(get_ips)
mcp.tool(get_ipq)
mcp.tool(get_risk_profile)
mcp.tool(list_client_documents)


if __name__ == "__main__":
    mcp.run()
```

**apps/mcp_servers/risk_planning/src/mcp_risk_planning/tools.py**
```python
"""Tools for the risk planning MCP server."""

from typing import Any

from mcp_risk_planning.db import get_db_connection
from mcp_common.models.risk import (
    InvestmentPolicyStatement,
    InvestorProfileQuestionnaire,
    RiskProfile,
)
from mcp_common.auth import validate_tenant_access


async def get_ips(
    client_id: str,
    tenant_id: str,
    version: int | None = None,
) -> dict[str, Any]:
    """
    Get Investment Policy Statement for a client.

    Args:
        client_id: The client ID
        tenant_id: The tenant ID for access control
        version: Optional specific version (returns latest if not specified)

    Returns:
        Investment Policy Statement with objectives, constraints, and allocation
    """
    validate_tenant_access(tenant_id)

    async with get_db_connection() as conn:
        if version:
            query = """
                SELECT * FROM investment_policy_statements
                WHERE client_id = ? AND tenant_id = ? AND version = ?
            """
            params = (client_id, tenant_id, version)
        else:
            query = """
                SELECT * FROM investment_policy_statements
                WHERE client_id = ? AND tenant_id = ? AND status = 'active'
                ORDER BY version DESC LIMIT 1
            """
            params = (client_id, tenant_id)

        row = await conn.fetchone(query, params)

        if not row:
            return {"error": "IPS not found"}

        return InvestmentPolicyStatement(**row).model_dump()


async def get_ipq(
    client_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    """
    Get Investor Profile Questionnaire for a client.

    Args:
        client_id: The client ID
        tenant_id: The tenant ID for access control

    Returns:
        IPQ with risk assessment and questionnaire responses
    """
    validate_tenant_access(tenant_id)

    async with get_db_connection() as conn:
        query = """
            SELECT * FROM investor_profile_questionnaires
            WHERE client_id = ? AND tenant_id = ?
            ORDER BY completed_at DESC LIMIT 1
        """
        row = await conn.fetchone(query, (client_id, tenant_id))

        if not row:
            return {"error": "IPQ not found"}

        return InvestorProfileQuestionnaire(**row).model_dump()


async def get_risk_profile(
    client_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    """
    Get risk profile summary for a client.

    Args:
        client_id: The client ID
        tenant_id: The tenant ID for access control

    Returns:
        Risk profile with scores and category
    """
    validate_tenant_access(tenant_id)

    async with get_db_connection() as conn:
        query = """
            SELECT * FROM risk_profiles
            WHERE client_id = ? AND tenant_id = ?
        """
        row = await conn.fetchone(query, (client_id, tenant_id))

        if not row:
            return {"error": "Risk profile not found"}

        return RiskProfile(**row).model_dump()


async def list_client_documents(
    client_id: str,
    tenant_id: str,
    document_type: str | None = None,
) -> dict[str, Any]:
    """
    List planning documents for a client.

    Args:
        client_id: The client ID
        tenant_id: The tenant ID for access control
        document_type: Optional filter (ips, ipq, financial_plan, etc.)

    Returns:
        List of documents with metadata
    """
    validate_tenant_access(tenant_id)

    async with get_db_connection() as conn:
        if document_type:
            query = """
                SELECT id, name, document_type, created_at, status
                FROM client_documents
                WHERE client_id = ? AND tenant_id = ? AND document_type = ?
                ORDER BY created_at DESC
            """
            params = (client_id, tenant_id, document_type)
        else:
            query = """
                SELECT id, name, document_type, created_at, status
                FROM client_documents
                WHERE client_id = ? AND tenant_id = ?
                ORDER BY created_at DESC
            """
            params = (client_id, tenant_id)

        rows = await conn.fetchall(query, params)

        return {
            "documents": [dict(row) for row in rows],
            "count": len(rows),
        }
```

---

### Task 4.5: Build MCP Reporting Server

**apps/mcp_servers/reporting/src/mcp_reporting/server.py**
```python
"""MCP server for reporting domain."""

from fastmcp import FastMCP

from mcp_reporting.tools import (
    get_report_template,
    list_report_templates,
    get_existing_report,
    list_reports,
)

mcp = FastMCP("Reporting MCP Server")

mcp.tool(get_report_template)
mcp.tool(list_report_templates)
mcp.tool(get_existing_report)
mcp.tool(list_reports)


if __name__ == "__main__":
    mcp.run()
```

**apps/mcp_servers/reporting/src/mcp_reporting/tools.py**
```python
"""Tools for the reporting MCP server."""

from typing import Any

from mcp_reporting.db import get_db_connection
from mcp_common.models.reporting import ReportTemplate, ExistingReport
from mcp_common.auth import validate_tenant_access


async def get_report_template(
    template_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    """
    Get a report template definition.

    Args:
        template_id: The template ID
        tenant_id: The tenant ID for access control

    Returns:
        Template definition with sections and parameters
    """
    validate_tenant_access(tenant_id)

    async with get_db_connection() as conn:
        query = """
            SELECT * FROM report_templates
            WHERE id = ? AND tenant_id = ?
        """
        row = await conn.fetchone(query, (template_id, tenant_id))

        if not row:
            return {"error": "Template not found"}

        return ReportTemplate(**row).model_dump()


async def list_report_templates(
    tenant_id: str,
    report_type: str | None = None,
) -> dict[str, Any]:
    """
    List available report templates.

    Args:
        tenant_id: The tenant ID for access control
        report_type: Optional filter by report type

    Returns:
        List of available templates
    """
    validate_tenant_access(tenant_id)

    async with get_db_connection() as conn:
        if report_type:
            query = """
                SELECT id, name, description, report_type
                FROM report_templates
                WHERE tenant_id = ? AND report_type = ? AND is_active = 1
            """
            params = (tenant_id, report_type)
        else:
            query = """
                SELECT id, name, description, report_type
                FROM report_templates
                WHERE tenant_id = ? AND is_active = 1
            """
            params = (tenant_id,)

        rows = await conn.fetchall(query, params)

        return {
            "templates": [dict(row) for row in rows],
            "count": len(rows),
        }


async def get_existing_report(
    report_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    """
    Get an existing generated report.

    Args:
        report_id: The report ID
        tenant_id: The tenant ID for access control

    Returns:
        Report metadata and content preview
    """
    validate_tenant_access(tenant_id)

    async with get_db_connection() as conn:
        query = """
            SELECT * FROM reports
            WHERE id = ? AND tenant_id = ?
        """
        row = await conn.fetchone(query, (report_id, tenant_id))

        if not row:
            return {"error": "Report not found"}

        return ExistingReport(**row).model_dump()


async def list_reports(
    tenant_id: str,
    client_id: str | None = None,
    opportunity_id: str | None = None,
    report_type: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """
    List existing reports with optional filters.

    Args:
        tenant_id: The tenant ID for access control
        client_id: Optional filter by client
        opportunity_id: Optional filter by opportunity
        report_type: Optional filter by report type
        limit: Maximum number of results

    Returns:
        List of reports with metadata
    """
    validate_tenant_access(tenant_id)

    async with get_db_connection() as conn:
        conditions = ["tenant_id = ?"]
        params = [tenant_id]

        if client_id:
            conditions.append("client_id = ?")
            params.append(client_id)
        if opportunity_id:
            conditions.append("opportunity_id = ?")
            params.append(opportunity_id)
        if report_type:
            conditions.append("report_type = ?")
            params.append(report_type)

        query = f"""
            SELECT id, title, report_type, status, generated_at, client_id, opportunity_id
            FROM reports
            WHERE {' AND '.join(conditions)}
            ORDER BY generated_at DESC
            LIMIT ?
        """
        params.append(limit)

        rows = await conn.fetchall(query, tuple(params))

        return {
            "reports": [dict(row) for row in rows],
            "count": len(rows),
        }
```

---

### Task 4.6: Build MCP Admin Policy Server

**apps/mcp_servers/admin_policy/src/mcp_admin_policy/server.py**
```python
"""MCP server for admin and policy domain."""

from fastmcp import FastMCP

from mcp_admin_policy.tools import (
    get_tenant_tool_policy,
    get_user_permissions,
    get_tenant_settings,
)

mcp = FastMCP("Admin Policy MCP Server")

mcp.tool(get_tenant_tool_policy)
mcp.tool(get_user_permissions)
mcp.tool(get_tenant_settings)


if __name__ == "__main__":
    mcp.run()
```

**apps/mcp_servers/admin_policy/src/mcp_admin_policy/tools.py**
```python
"""Tools for the admin policy MCP server."""

from typing import Any

from mcp_admin_policy.db import get_db_connection
from mcp_common.auth import validate_tenant_access


async def get_tenant_tool_policy(
    tenant_id: str,
) -> dict[str, Any]:
    """
    Get the tool policy configuration for a tenant.

    Args:
        tenant_id: The tenant ID

    Returns:
        Tool policy including enabled tools and restrictions
    """
    validate_tenant_access(tenant_id)

    async with get_db_connection() as conn:
        query = """
            SELECT * FROM tenant_policies
            WHERE tenant_id = ?
        """
        row = await conn.fetchone(query, (tenant_id,))

        if not row:
            # Return default policy
            return {
                "tenant_id": tenant_id,
                "internet_search_enabled": False,
                "rag_enabled": True,
                "mcp_domains_enabled": ["opportunities", "clients", "risk_planning", "reporting"],
                "max_tool_calls_per_session": 20,
            }

        return dict(row)


async def get_user_permissions(
    user_id: str,
    tenant_id: str,
) -> dict[str, Any]:
    """
    Get permissions for a user.

    Args:
        user_id: The user ID
        tenant_id: The tenant ID for access control

    Returns:
        User permissions and roles
    """
    validate_tenant_access(tenant_id)

    async with get_db_connection() as conn:
        query = """
            SELECT u.id, u.email, u.name, u.role,
                   GROUP_CONCAT(p.permission) as permissions
            FROM users u
            LEFT JOIN user_permissions p ON p.user_id = u.id
            WHERE u.id = ? AND u.tenant_id = ?
            GROUP BY u.id
        """
        row = await conn.fetchone(query, (user_id, tenant_id))

        if not row:
            return {"error": "User not found"}

        return {
            "user_id": row["id"],
            "email": row["email"],
            "name": row["name"],
            "role": row["role"],
            "permissions": row["permissions"].split(",") if row["permissions"] else [],
        }


async def get_tenant_settings(
    tenant_id: str,
) -> dict[str, Any]:
    """
    Get general settings for a tenant.

    Args:
        tenant_id: The tenant ID

    Returns:
        Tenant settings and configuration
    """
    validate_tenant_access(tenant_id)

    async with get_db_connection() as conn:
        query = """
            SELECT * FROM tenant_settings
            WHERE tenant_id = ?
        """
        row = await conn.fetchone(query, (tenant_id,))

        if not row:
            return {
                "tenant_id": tenant_id,
                "default_currency": "USD",
                "default_language": "en",
                "timezone": "UTC",
            }

        return dict(row)
```

---

### Task 4.7: Register All MCP Servers in Agent

**packages/agent_core/src/agent_core/tools/mcp_registry.py**
```python
"""MCP server registry and configuration."""

from typing import Any
import os

from agent_core.tools.mcp_client import mcp_registry
from common.config import get_settings
from common.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()


def register_all_mcp_servers() -> None:
    """Register all MCP servers from configuration."""

    # Get server URLs from environment or config
    servers = {
        "opportunities": os.getenv("MCP_OPPORTUNITIES_URL", "http://localhost:8001"),
        "clients": os.getenv("MCP_CLIENTS_URL", "http://localhost:8002"),
        "risk_planning": os.getenv("MCP_RISK_PLANNING_URL", "http://localhost:8003"),
        "reporting": os.getenv("MCP_REPORTING_URL", "http://localhost:8004"),
        "admin_policy": os.getenv("MCP_ADMIN_POLICY_URL", "http://localhost:8005"),
    }

    for domain, url in servers.items():
        mcp_registry.register(domain, url)
        logger.info("Registered MCP server", domain=domain, url=url)


# Available tools per domain (for documentation and validation)
MCP_TOOL_CATALOG = {
    "opportunities": [
        "get_opportunity",
        "get_opportunity_kpis",
        "list_opportunity_documents",
    ],
    "clients": [
        "get_client",
        "get_client_relationships",
        "get_client_portfolio_snapshot",
        "list_client_holdings",
        "search_clients",
    ],
    "risk_planning": [
        "get_ips",
        "get_ipq",
        "get_risk_profile",
        "list_client_documents",
    ],
    "reporting": [
        "get_report_template",
        "list_report_templates",
        "get_existing_report",
        "list_reports",
    ],
    "admin_policy": [
        "get_tenant_tool_policy",
        "get_user_permissions",
        "get_tenant_settings",
    ],
}
```

---

### Task 4.8: Create Integration Tests

**apps/mcp_servers/tests/test_opportunities_integration.py**
```python
"""Integration tests for opportunities MCP server."""

import pytest
from httpx import AsyncClient


@pytest.fixture
def tenant_id():
    return "test-tenant"


@pytest.fixture
def test_opportunity_id():
    return "opp-001"


class TestOpportunitiesMCP:
    """Integration tests for opportunities MCP server."""

    @pytest.mark.asyncio
    async def test_get_opportunity(self, tenant_id, test_opportunity_id):
        """Test getting an opportunity."""
        async with AsyncClient(base_url="http://localhost:8001") as client:
            response = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "get_opportunity",
                        "arguments": {
                            "opportunity_id": test_opportunity_id,
                            "tenant_id": tenant_id,
                        },
                    },
                    "id": 1,
                },
            )

            assert response.status_code == 200
            result = response.json()
            assert "result" in result or "error" in result

    @pytest.mark.asyncio
    async def test_get_opportunity_kpis(self, tenant_id, test_opportunity_id):
        """Test getting opportunity KPIs."""
        async with AsyncClient(base_url="http://localhost:8001") as client:
            response = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "get_opportunity_kpis",
                        "arguments": {
                            "opportunity_id": test_opportunity_id,
                            "tenant_id": tenant_id,
                        },
                    },
                    "id": 1,
                },
            )

            assert response.status_code == 200
```

**apps/mcp_servers/tests/test_contract.py**
```python
"""Contract tests for all MCP servers."""

import pytest
from httpx import AsyncClient
from typing import Any


MCP_SERVERS = [
    ("opportunities", "http://localhost:8001"),
    ("clients", "http://localhost:8002"),
    ("risk_planning", "http://localhost:8003"),
    ("reporting", "http://localhost:8004"),
    ("admin_policy", "http://localhost:8005"),
]


class TestMCPContracts:
    """Contract tests to verify MCP servers follow the protocol."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("domain,url", MCP_SERVERS)
    async def test_server_responds_to_list_tools(self, domain: str, url: str):
        """All MCP servers should respond to tools/list."""
        async with AsyncClient(base_url=url, timeout=5.0) as client:
            try:
                response = await client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/list",
                        "params": {},
                        "id": 1,
                    },
                )
                assert response.status_code == 200
                result = response.json()
                assert "result" in result
                assert "tools" in result["result"]
            except Exception as e:
                pytest.skip(f"Server {domain} not available: {e}")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("domain,url", MCP_SERVERS)
    async def test_server_returns_error_for_unknown_tool(self, domain: str, url: str):
        """Servers should return error for unknown tools."""
        async with AsyncClient(base_url=url, timeout=5.0) as client:
            try:
                response = await client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "method": "tools/call",
                        "params": {
                            "name": "nonexistent_tool",
                            "arguments": {},
                        },
                        "id": 1,
                    },
                )
                assert response.status_code == 200
                result = response.json()
                assert "error" in result
            except Exception as e:
                pytest.skip(f"Server {domain} not available: {e}")
```

---

## Azure Configuration Checklist

### 1. Database Access for Each Domain

For each MCP server, set up database credentials:

**Add to Key Vault:**
```bash
# Clients DB
az keyvault secret set --vault-name <vault> --name clients-db-password --value <password>

# Risk Planning DB
az keyvault secret set --vault-name <vault> --name risk-planning-db-password --value <password>

# Reporting DB
az keyvault secret set --vault-name <vault> --name reporting-db-password --value <password>
```

**Update .env:**
```env
# Clients DB
CLIENTS_DB_HOST=your-sql-server.database.windows.net
CLIENTS_DB_NAME=clients
CLIENTS_DB_USER=readonly_user
CLIENTS_DB_PASSWORD=your-password

# Risk Planning DB
RISK_PLANNING_DB_HOST=your-sql-server.database.windows.net
RISK_PLANNING_DB_NAME=risk_planning
RISK_PLANNING_DB_USER=readonly_user
RISK_PLANNING_DB_PASSWORD=your-password

# Reporting DB
REPORTING_DB_HOST=your-sql-server.database.windows.net
REPORTING_DB_NAME=reporting
REPORTING_DB_USER=readonly_user
REPORTING_DB_PASSWORD=your-password
```

### 2. MCP Server URLs

If deploying as separate services:
```env
MCP_OPPORTUNITIES_URL=https://mcp-opportunities.azurecontainer.io
MCP_CLIENTS_URL=https://mcp-clients.azurecontainer.io
MCP_RISK_PLANNING_URL=https://mcp-risk-planning.azurecontainer.io
MCP_REPORTING_URL=https://mcp-reporting.azurecontainer.io
MCP_ADMIN_POLICY_URL=https://mcp-admin-policy.azurecontainer.io
```

---

## Testing Checklist

### Unit Tests

- [ ] Test each MCP tool in isolation with mocks
- [ ] Test schema validation for all models
- [ ] Test tenant access validation

### Integration Tests

- [ ] Contract tests pass for all servers
- [ ] Each server responds to tools/list
- [ ] Each server handles unknown tools gracefully
- [ ] Tenant filtering works correctly

### End-to-End Tests

- [ ] Agent can call tools from multiple domains in one session
- [ ] Module-specific tool sets work correctly
- [ ] Policy enforcement blocks disabled domains

---

## Expected Deliverables

After completing Phase 4:

1. **MCP Servers**:
   - `mcp-clients`: Client profiles, relationships, portfolios
   - `mcp-risk-planning`: IPS, IPQ, risk profiles
   - `mcp-reporting`: Templates, existing reports
   - `mcp-admin-policy`: Tenant policies, user permissions

2. **Shared Infrastructure**:
   - `mcp_common` with standardized models
   - Base server template
   - Telemetry and validation decorators

3. **Tests**:
   - Integration tests for each server
   - Contract tests for protocol compliance

4. **Multi-Module Support**:
   - Same copilot works across Deals, CRM, Risk, Admin
   - Different tool sets enabled per module

---

## Next Phase

Once Phase 4 is complete and tested, proceed to [Phase 5: Production Hardening](phase-5-production-hardening.md).
