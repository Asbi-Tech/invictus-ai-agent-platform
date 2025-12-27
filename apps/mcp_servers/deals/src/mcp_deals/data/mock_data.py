"""Mock data store for Deals MCP server.

This module provides placeholder data for development.
In production, this would be replaced with actual Cosmos DB queries.
"""

MOCK_OPPORTUNITIES = {
    "opp-001": {
        "opportunity_id": "opp-001",
        "name": "Wonder Group Inc",
        "status": "active",
        "type": "food_technology",
        "target_raise": "SAFE Note",
        "current_committed": "Confidential",
        "close_date": "2025-06-30",
        "manager": "Marc Lore (Founder & CEO)",
        "vintage_year": 2024,
        "sector": "Food Technology",
        "geography": "United States",
        "minimum_investment": "SAFE Note Structure",
        "management_fee": "N/A",
        "carry": "N/A",
        "description": "Vertically integrated food delivery platform controlling the entire value chain from restaurants to delivery. Proprietary FLASH kitchen technology enables 40 cuisines from 3,000 sq ft HDR locations.",
        "stage": "Due Diligence",
        "risk_rating": "Medium",
        "gov_arr_2023": 407000000,
        "gov_arr_target_2027": 4200000000,
        "investment_structure": "SAFE Note with 40% guaranteed IRR",
        "created_at": "2024-11-01T00:00:00Z",
        "updated_at": "2024-12-27T00:00:00Z",
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
            "Wonder Group Inc represents a compelling investment opportunity in the "
            "food technology space. Founded by Marc Lore (proven serial entrepreneur with "
            "$3.5B+ in prior exits), Wonder is building the first fully vertically integrated "
            "food delivery platform with proprietary kitchen technology."
        ),
        "key_findings": [
            "Proven founder with track record (Jet.com sold to Walmart for $3.3B)",
            "First vertically integrated food delivery platform controlling entire value chain",
            "Proprietary FLASH technology enabling 40 cuisines from 3,000 sq ft HDR locations",
            "Strong unit economics: LTV/CAC ~20x, NPS 60+ vs negative for incumbents",
            "Multiple revenue streams: HDRs, Blue Apron, WonderWorks B2B, 3P marketplace",
            "Rapid growth: $407M GOV ARR (2023) targeting $4.2B+ by 2027",
        ],
        "concerns": [
            "High capital intensity of vertical integration model",
            "Execution risk on aggressive HDR expansion plan",
            "Competition from well-funded incumbents (DoorDash, Uber Eats)",
            "Key person dependency on founder Marc Lore",
        ],
        "investment_thesis": (
            "Wonder targets the $1 trillion food and delivery market by solving structural "
            "inefficiencies through vertical integration. Proprietary FLASH technology and "
            "High-Density Restaurants (HDRs) enable 30-min delivery, 97% order accuracy, and "
            "superior margins vs traditional aggregators. Platform approach with multiple revenue "
            "streams de-risks single-channel dependency."
        ),
        "financial_highlights": {
            "target_irr": "40% guaranteed at liquidity",
            "target_moic": "2.7x-5.4x at IPO",
            "gov_arr_2023": "$407M",
            "gov_arr_target_2027": "$4.2B+",
            "structure": "SAFE Note with 1.5x liquidation preference",
            "base_case_exit": "2027 IPO",
        },
        "conclusion": (
            "Recommend proceeding to full due diligence. Strong founder, differentiated "
            "technology, attractive unit economics, and guaranteed 40% IRR structure provide "
            "compelling risk-adjusted exposure to category-defining platform."
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
        "memo_date": "2024-12-27",
        "version": "1.0",
        "author": "Investment Committee",
        "status": "draft",
        "sections": {
            "executive_summary": (
                "This investment memo recommends an investment in Wonder Group Inc via "
                "SAFE Note structure with guaranteed 40% gross IRR at liquidity. Wonder is "
                "building the first fully vertically integrated food delivery platform, "
                "targeting $100B revenue by 2035 in the $1 trillion food and delivery market."
            ),
            "investment_thesis": (
                "Wonder solves structural inefficiencies in food delivery through complete "
                "vertical integration and proprietary technology. The FLASH kitchen system "
                "enables 40 cuisines from 3,000 sq ft HDR locations with 30-min delivery, "
                "97% order accuracy, and superior unit economics vs incumbents. Platform model "
                "with multiple revenue streams (HDRs, Blue Apron, WonderWorks B2B, 3P marketplace) "
                "provides diversification and path to $4.2B+ GOV ARR by 2027."
            ),
            "manager_assessment": (
                "Marc Lore is a proven serial entrepreneur with $3.5B+ in prior exits "
                "(Diapers.com, Jet.com sold to Walmart for $3.3B). Strong execution track "
                "record in e-commerce and logistics. Management team includes veterans from "
                "Amazon, Uber, and leading restaurant groups. Over $100M invested in "
                "proprietary FLASH technology over 5+ years."
            ),
            "risk_analysis": (
                "Key risks include: (1) High capital intensity of vertical integration model, "
                "(2) Execution risk on aggressive HDR expansion, (3) Competition from well-funded "
                "incumbents (DoorDash $60B+ market cap, Uber Eats), (4) Key person dependency on "
                "Marc Lore. Mitigants include guaranteed 40% IRR structure, 1.5x liquidation "
                "preference downside protection, strong unit economics (LTV/CAC ~20x), and "
                "multiple revenue diversification."
            ),
            "terms_analysis": (
                "Attractive SAFE Note structure: Guaranteed 40% gross IRR at any successful "
                "liquidity event, 2.7x-5.4x MOIC at IPO scenarios (2027-2029), 1.5x liquidation "
                "preference provides downside protection. Strategic partnerships include $100M "
                "investment from Nestlé. Base case exit: 2027 IPO with long-term valuation "
                "potential of $60-100B."
            ),
            "recommendation": (
                "The Investment Committee recommends proceeding with investment in Wonder Group Inc "
                "SAFE Note, subject to completion of legal due diligence, technology validation, "
                "and reference checks with industry experts and prior investors."
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
            "date": "2024-12-27T14:30:00Z",
            "action": "Investment memo draft created",
            "user": "pm@firm.com",
            "type": "document",
            "details": {"document_type": "investment_memo", "version": "1.0"},
        },
        {
            "activity_id": "act-002",
            "date": "2024-12-20T10:00:00Z",
            "action": "Technology validation call scheduled",
            "user": "analyst@firm.com",
            "type": "meeting",
            "details": {"meeting_date": "2025-01-15", "attendees": ["Marc Lore", "CTO", "IC"]},
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
            "action": "Documents received - DDQ, Teaser, Overview",
            "user": "analyst@firm.com",
            "type": "document",
            "details": {"document_count": 4, "categories": ["DDQ", "Teaser", "Company Overview"]},
        },
        {
            "activity_id": "act-006",
            "date": "2024-11-01T08:00:00Z",
            "action": "Opportunity created",
            "user": "system",
            "type": "system",
            "details": {"source": "Direct Outreach - Marc Lore"},
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
