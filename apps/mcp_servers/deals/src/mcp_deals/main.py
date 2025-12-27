"""Entry point for Deals MCP server.

Run with:
    python -m mcp_deals.main

Or:
    uvicorn mcp_deals.main:app --host 0.0.0.0 --port 8001
"""

import uvicorn

from mcp_deals.server import create_app

# Create the FastAPI app
app = create_app()


if __name__ == "__main__":
    uvicorn.run(
        "mcp_deals.main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
    )
