"""Telemetry utilities for MCP servers."""

import time
from contextlib import contextmanager
from typing import Any, Generator

from common.logging import get_logger

logger = get_logger(__name__)


@contextmanager
def track_tool_call(
    tool_name: str,
    tenant_id: str,
    user_id: str | None = None,
) -> Generator[dict[str, Any], None, None]:
    """
    Context manager to track tool call metrics.

    Records timing, success/failure, and logs the result.

    Usage:
        with track_tool_call("get_opportunity", tenant_id, user_id) as metrics:
            result = await do_work()
            metrics["result_count"] = len(result)

    Args:
        tool_name: Name of the tool being called
        tenant_id: The tenant ID
        user_id: Optional user ID

    Yields:
        Dictionary to store metrics that will be logged on completion
    """
    metrics: dict[str, Any] = {
        "tool_name": tool_name,
        "tenant_id": tenant_id,
        "user_id": user_id,
        "start_time": time.time(),
    }

    try:
        yield metrics
        metrics["success"] = True
    except Exception as e:
        metrics["success"] = False
        metrics["error"] = str(e)
        metrics["error_type"] = type(e).__name__
        raise
    finally:
        metrics["duration_ms"] = (time.time() - metrics["start_time"]) * 1000

        log_data = {
            "tool_name": tool_name,
            "tenant_id": tenant_id,
            "duration_ms": round(metrics["duration_ms"], 2),
            "success": metrics.get("success", False),
        }

        if user_id:
            log_data["user_id"] = user_id

        if not metrics.get("success"):
            log_data["error"] = metrics.get("error")
            log_data["error_type"] = metrics.get("error_type")

        # Add any custom metrics
        for key in ["result_count", "rows_returned", "cache_hit"]:
            if key in metrics:
                log_data[key] = metrics[key]

        if metrics.get("success"):
            logger.info("Tool call completed", **log_data)
        else:
            logger.warning("Tool call failed", **log_data)


class MetricsCollector:
    """
    Collector for aggregating metrics across multiple tool calls.

    Usage:
        collector = MetricsCollector()
        collector.record_call("get_opportunity", 150.5, success=True)
        collector.record_call("list_documents", 200.0, success=True)
        summary = collector.get_summary()
    """

    def __init__(self):
        self._calls: list[dict[str, Any]] = []

    def record_call(
        self,
        tool_name: str,
        duration_ms: float,
        success: bool = True,
        error: str | None = None,
    ) -> None:
        """
        Record a tool call.

        Args:
            tool_name: Name of the tool
            duration_ms: Duration in milliseconds
            success: Whether the call succeeded
            error: Error message if failed
        """
        self._calls.append(
            {
                "tool_name": tool_name,
                "duration_ms": duration_ms,
                "success": success,
                "error": error,
                "timestamp": time.time(),
            }
        )

    def get_summary(self) -> dict[str, Any]:
        """
        Get a summary of all recorded calls.

        Returns:
            Dictionary with aggregated metrics
        """
        if not self._calls:
            return {
                "total_calls": 0,
                "successful_calls": 0,
                "failed_calls": 0,
                "total_duration_ms": 0,
                "avg_duration_ms": 0,
            }

        successful = [c for c in self._calls if c["success"]]
        failed = [c for c in self._calls if not c["success"]]
        total_duration = sum(c["duration_ms"] for c in self._calls)

        return {
            "total_calls": len(self._calls),
            "successful_calls": len(successful),
            "failed_calls": len(failed),
            "total_duration_ms": round(total_duration, 2),
            "avg_duration_ms": round(total_duration / len(self._calls), 2),
            "tools_called": list(set(c["tool_name"] for c in self._calls)),
        }

    def clear(self) -> None:
        """Clear all recorded calls."""
        self._calls.clear()
