#!/bin/bash
set -e

echo "=== Invictus AI Agent Platform - Local Development Setup ==="
echo ""

# Check Python version
python_version=$(python3 --version 2>&1 | cut -d' ' -f2 | cut -d'.' -f1,2)
required_version="3.11"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "Error: Python $required_version or higher is required. Found: $python_version"
    exit 1
fi

echo "Python version: $python_version"

# Create virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo ""
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
echo ""
echo "Activating virtual environment..."
source .venv/bin/activate

# Upgrade pip
echo ""
echo "Upgrading pip..."
pip install --upgrade pip

# Install development dependencies
echo ""
echo "Installing development dependencies..."
pip install -r requirements/dev.txt

# Install shared packages in editable mode
echo ""
echo "Installing shared packages in editable mode..."
pip install -e packages/common
pip install -e packages/mcp_common
pip install -e packages/agent_core

# Install agent_api dependencies
echo ""
echo "Installing agent_api dependencies..."
pip install -r requirements/agent_api.txt

# Copy .env.example if .env doesn't exist
if [ ! -f ".env" ]; then
    echo ""
    echo "Creating .env from .env.example..."
    cp .env.example .env
    echo ""
    echo "IMPORTANT: Please update .env with your actual configuration values."
fi

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo "  1. Activate the virtual environment:"
echo "     source .venv/bin/activate"
echo ""
echo "  2. Update .env with your configuration values"
echo ""
echo "  3. Run the agent API:"
echo "     uvicorn apps.agent_api.src.agent_api.main:app --reload"
echo ""
echo "  4. Run tests:"
echo "     pytest"
echo ""
echo "  5. Run linting:"
echo "     ruff check ."
echo "     ruff format ."
echo ""
