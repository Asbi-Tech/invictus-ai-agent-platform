"""SSE Callback Registry.

This module provides a registry for SSE callbacks that can't be serialized
in LangGraph checkpoints. On resume, nodes look up callbacks here.
"""

from typing import Any, Callable, Awaitable

# Type alias for SSE callback
SSECallbackType = Callable[[str, str | dict, str | None], Awaitable[None]]

# Global callback registry keyed by session_id
_SSE_CALLBACK_REGISTRY: dict[str, SSECallbackType] = {}


def register_sse_callback(session_id: str, callback: SSECallbackType) -> None:
    """Register an SSE callback for a session."""
    _SSE_CALLBACK_REGISTRY[session_id] = callback


def get_sse_callback(session_id: str) -> SSECallbackType | None:
    """Get the SSE callback for a session from the registry."""
    return _SSE_CALLBACK_REGISTRY.get(session_id)


def unregister_sse_callback(session_id: str) -> None:
    """Remove the SSE callback for a session from the registry."""
    _SSE_CALLBACK_REGISTRY.pop(session_id, None)


def get_callback_for_state(state: dict[str, Any]) -> SSECallbackType | None:
    """
    Get SSE callback for a state dict.

    First checks if state has a callable sse_callback. If not (or if it's
    a serialized string from checkpoint), falls back to the registry.

    Usage in nodes:
        from common.callback_registry import get_callback_for_state

        sse_callback = get_callback_for_state(state)
        if sse_callback:
            await sse_callback(event_type, data, node_name)
    """
    # First try to get from state
    callback = state.get("sse_callback")
    if callback is not None and callable(callback):
        return callback

    # Fall back to registry
    session_id = state.get("session_id")
    if session_id:
        return get_sse_callback(session_id)

    return None
