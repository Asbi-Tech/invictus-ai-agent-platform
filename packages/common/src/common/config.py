"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment
    environment: Literal["development", "staging", "production"] = "development"
    log_level: str = "INFO"

    # Azure OpenAI
    azure_openai_endpoint: str = Field(..., description="Azure OpenAI endpoint URL")
    azure_openai_api_key: str = Field(..., description="Azure OpenAI API key")
    azure_openai_deployment_name: str = Field(default="gpt-4o")
    azure_openai_api_version: str = Field(default="2024-02-01")

    # Cosmos DB
    cosmos_endpoint: str = Field(..., description="Cosmos DB endpoint URL")
    cosmos_key: str = Field(..., description="Cosmos DB primary key")
    cosmos_database_name: str = Field(default="invictus-copilot")
    cosmos_sessions_container: str = Field(default="sessions")
    cosmos_checkpoints_container: str = Field(default="checkpoints")
    cosmos_artifacts_container: str = Field(default="artifacts")

    # RAG Gateway
    rag_gateway_url: str = Field(..., description="RAG Gateway base URL")
    rag_gateway_api_key: str = Field(default="", description="RAG Gateway API key")

    # Tavily (optional)
    tavily_api_key: str = Field(default="", description="Tavily API key for internet search")

    # MCP Server URLs
    mcp_deals_url: str = Field(default="http://localhost:8001")

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
