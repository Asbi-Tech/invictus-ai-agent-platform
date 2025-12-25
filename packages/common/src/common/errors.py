"""Custom exception classes for the Invictus AI platform."""

from typing import Any


class InvictusError(Exception):
    """Base exception for all Invictus AI platform errors."""

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        if self.details:
            return f"{self.message} - Details: {self.details}"
        return self.message


class ConfigurationError(InvictusError):
    """Raised when there's a configuration issue."""

    pass


class AuthenticationError(InvictusError):
    """Raised when authentication fails."""

    pass


class AuthorizationError(InvictusError):
    """Raised when user lacks permission for an operation."""

    pass


class ValidationError(InvictusError):
    """Raised when input validation fails."""

    pass


class ToolExecutionError(InvictusError):
    """Raised when a tool execution fails."""

    def __init__(
        self,
        message: str,
        tool_name: str,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, details)
        self.tool_name = tool_name


class RAGGatewayError(InvictusError):
    """Raised when RAG Gateway communication fails."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, details)
        self.status_code = status_code


class MCPError(InvictusError):
    """Raised when MCP server communication fails."""

    def __init__(
        self,
        message: str,
        server_name: str,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, details)
        self.server_name = server_name


class SessionNotFoundError(InvictusError):
    """Raised when a session is not found in storage."""

    def __init__(self, session_id: str):
        super().__init__(f"Session not found: {session_id}")
        self.session_id = session_id


class CheckpointError(InvictusError):
    """Raised when checkpoint save/load operations fail."""

    pass


class LLMError(InvictusError):
    """Raised when LLM operations fail."""

    def __init__(
        self,
        message: str,
        model: str | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, details)
        self.model = model


class RateLimitError(InvictusError):
    """Raised when rate limits are exceeded."""

    def __init__(
        self,
        message: str,
        retry_after: int | None = None,
        details: dict[str, Any] | None = None,
    ):
        super().__init__(message, details)
        self.retry_after = retry_after
