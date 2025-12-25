# Phase 5: Production Hardening

## Objectives

- Implement observability with Azure App Insights and OpenTelemetry
- Add reliability patterns (retries, circuit breakers, caching)
- Create evaluation framework (golden tests, citation checks)
- Build operational runbooks and documentation
- Prepare for security upgrades (Managed Identity path)

## Prerequisites

- Phases 0-4 completed
- All MCP servers deployed and tested
- Azure App Insights resource created
- Production-like environment available for testing

---

## Implementation Tasks

### Task 5.1: Set Up OpenTelemetry Integration

**packages/common/src/common/telemetry.py**
```python
"""OpenTelemetry setup and instrumentation."""

import os
from typing import Any

from opentelemetry import trace, metrics
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from azure.monitor.opentelemetry.exporter import (
    AzureMonitorTraceExporter,
    AzureMonitorMetricExporter,
)

from common.logging import get_logger

logger = get_logger(__name__)


def setup_telemetry(
    service_name: str,
    service_version: str = "0.1.0",
    environment: str = "development",
) -> None:
    """
    Set up OpenTelemetry with Azure Monitor exporters.

    Args:
        service_name: Name of the service (e.g., "agent-api", "mcp-opportunities")
        service_version: Version of the service
        environment: Deployment environment
    """
    connection_string = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")

    if not connection_string:
        logger.warning("App Insights connection string not configured, using console exporter")
        return

    # Create resource with service info
    resource = Resource.create({
        "service.name": service_name,
        "service.version": service_version,
        "deployment.environment": environment,
    })

    # Set up tracing
    trace_exporter = AzureMonitorTraceExporter(connection_string=connection_string)
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(trace_exporter))
    trace.set_tracer_provider(tracer_provider)

    # Set up metrics
    metric_exporter = AzureMonitorMetricExporter(connection_string=connection_string)
    metric_reader = PeriodicExportingMetricReader(
        exporter=metric_exporter,
        export_interval_millis=60000,  # Export every minute
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    logger.info("Telemetry initialized", service=service_name, environment=environment)


def instrument_fastapi(app) -> None:
    """Instrument a FastAPI application."""
    FastAPIInstrumentor.instrument_app(app)


def instrument_httpx() -> None:
    """Instrument HTTPX client."""
    HTTPXClientInstrumentor().instrument()


# Convenience getters
def get_tracer(name: str) -> trace.Tracer:
    """Get a tracer for the given name."""
    return trace.get_tracer(name)


def get_meter(name: str) -> metrics.Meter:
    """Get a meter for the given name."""
    return metrics.get_meter(name)
```

---

### Task 5.2: Create Custom Metrics

**packages/agent_core/src/agent_core/observability/metrics.py**
```python
"""Custom metrics for agent observability."""

from opentelemetry import metrics

from common.telemetry import get_meter

meter = get_meter("agent_core")

# Counters
tool_calls_total = meter.create_counter(
    name="agent.tool_calls.total",
    description="Total number of tool calls",
    unit="1",
)

hitl_requests_total = meter.create_counter(
    name="agent.hitl_requests.total",
    description="Total number of HITL requests",
    unit="1",
)

artifacts_created_total = meter.create_counter(
    name="agent.artifacts_created.total",
    description="Total number of artifacts created",
    unit="1",
)

errors_total = meter.create_counter(
    name="agent.errors.total",
    description="Total number of errors",
    unit="1",
)

# Histograms
tool_call_duration = meter.create_histogram(
    name="agent.tool_call.duration",
    description="Duration of tool calls in milliseconds",
    unit="ms",
)

session_duration = meter.create_histogram(
    name="agent.session.duration",
    description="Duration of agent sessions in seconds",
    unit="s",
)

response_tokens = meter.create_histogram(
    name="agent.response.tokens",
    description="Number of tokens in responses",
    unit="1",
)

# Gauges (using up-down counter as OpenTelemetry doesn't have gauge)
active_sessions = meter.create_up_down_counter(
    name="agent.sessions.active",
    description="Number of active sessions",
    unit="1",
)


def record_tool_call(
    tool_name: str,
    domain: str,
    success: bool,
    duration_ms: float,
    tenant_id: str,
) -> None:
    """Record a tool call metric."""
    attributes = {
        "tool_name": tool_name,
        "domain": domain,
        "success": str(success),
        "tenant_id": tenant_id,
    }

    tool_calls_total.add(1, attributes)
    tool_call_duration.record(duration_ms, attributes)


def record_hitl_request(
    hitl_type: str,
    tenant_id: str,
) -> None:
    """Record a HITL request metric."""
    hitl_requests_total.add(1, {
        "hitl_type": hitl_type,
        "tenant_id": tenant_id,
    })


def record_artifact_created(
    artifact_type: str,
    tenant_id: str,
) -> None:
    """Record an artifact creation metric."""
    artifacts_created_total.add(1, {
        "artifact_type": artifact_type,
        "tenant_id": tenant_id,
    })


def record_error(
    error_type: str,
    component: str,
    tenant_id: str = "unknown",
) -> None:
    """Record an error metric."""
    errors_total.add(1, {
        "error_type": error_type,
        "component": component,
        "tenant_id": tenant_id,
    })
```

---

### Task 5.3: Implement Retry and Circuit Breaker

**packages/common/src/common/resilience.py**
```python
"""Resilience patterns: retry, circuit breaker, timeout."""

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from typing import Any, Callable, Type

from common.logging import get_logger

logger = get_logger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""
    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 2  # Successes before closing from half-open
    timeout_seconds: float = 30.0  # Time before trying half-open
    excluded_exceptions: tuple[Type[Exception], ...] = ()


@dataclass
class CircuitBreaker:
    """Circuit breaker implementation."""
    name: str
    config: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: datetime | None = None

    def can_execute(self) -> bool:
        """Check if we can execute a call."""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if timeout has passed
            if self.last_failure_time:
                elapsed = datetime.utcnow() - self.last_failure_time
                if elapsed.total_seconds() >= self.config.timeout_seconds:
                    self.state = CircuitState.HALF_OPEN
                    self.success_count = 0
                    logger.info("Circuit breaker half-open", name=self.name)
                    return True
            return False

        # Half-open: allow one test call
        return True

    def record_success(self) -> None:
        """Record a successful call."""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                logger.info("Circuit breaker closed", name=self.name)
        elif self.state == CircuitState.CLOSED:
            # Reset failure count on success
            self.failure_count = 0

    def record_failure(self, exception: Exception) -> None:
        """Record a failed call."""
        # Check if this exception should be excluded
        if isinstance(exception, self.config.excluded_exceptions):
            return

        self.failure_count += 1
        self.last_failure_time = datetime.utcnow()

        if self.state == CircuitState.HALF_OPEN:
            # Any failure in half-open goes back to open
            self.state = CircuitState.OPEN
            logger.warning("Circuit breaker opened (from half-open)", name=self.name)
        elif self.state == CircuitState.CLOSED:
            if self.failure_count >= self.config.failure_threshold:
                self.state = CircuitState.OPEN
                logger.warning(
                    "Circuit breaker opened",
                    name=self.name,
                    failures=self.failure_count,
                )


# Global registry of circuit breakers
_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(name: str, config: CircuitBreakerConfig | None = None) -> CircuitBreaker:
    """Get or create a circuit breaker."""
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(name=name, config=config or CircuitBreakerConfig())
    return _circuit_breakers[name]


class CircuitBreakerOpen(Exception):
    """Exception raised when circuit breaker is open."""
    pass


def with_circuit_breaker(name: str, config: CircuitBreakerConfig | None = None):
    """Decorator to wrap a function with circuit breaker."""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cb = get_circuit_breaker(name, config)

            if not cb.can_execute():
                raise CircuitBreakerOpen(f"Circuit breaker '{name}' is open")

            try:
                result = await func(*args, **kwargs)
                cb.record_success()
                return result
            except Exception as e:
                cb.record_failure(e)
                raise

        return wrapper
    return decorator


@dataclass
class RetryConfig:
    """Configuration for retry logic."""
    max_attempts: int = 3
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    exponential_base: float = 2.0
    retryable_exceptions: tuple[Type[Exception], ...] = (Exception,)


def with_retry(config: RetryConfig | None = None):
    """Decorator to add retry logic to a function."""
    cfg = config or RetryConfig()

    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            delay = cfg.initial_delay_seconds

            for attempt in range(1, cfg.max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except cfg.retryable_exceptions as e:
                    last_exception = e
                    if attempt < cfg.max_attempts:
                        logger.warning(
                            "Retrying after error",
                            function=func.__name__,
                            attempt=attempt,
                            delay=delay,
                            error=str(e),
                        )
                        await asyncio.sleep(delay)
                        delay = min(delay * cfg.exponential_base, cfg.max_delay_seconds)
                    else:
                        logger.error(
                            "Max retries exceeded",
                            function=func.__name__,
                            attempts=cfg.max_attempts,
                            error=str(e),
                        )

            raise last_exception

        return wrapper
    return decorator


def with_timeout(seconds: float):
    """Decorator to add timeout to a function."""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
            except asyncio.TimeoutError:
                logger.error("Function timed out", function=func.__name__, timeout=seconds)
                raise

        return wrapper
    return decorator
```

---

### Task 5.4: Implement Response Caching

**packages/agent_core/src/agent_core/memory/cache.py**
```python
"""Caching layer for frequently accessed data."""

from datetime import datetime, timedelta
from typing import Any, Callable, TypeVar
from functools import wraps
import hashlib
import json

from common.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")


class CacheEntry:
    """A cache entry with expiration."""

    def __init__(self, value: Any, ttl_seconds: int):
        self.value = value
        self.expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)

    def is_expired(self) -> bool:
        return datetime.utcnow() > self.expires_at


class InMemoryCache:
    """Simple in-memory cache with TTL."""

    def __init__(self, max_size: int = 1000):
        self._cache: dict[str, CacheEntry] = {}
        self._max_size = max_size

    def _make_key(self, prefix: str, *args, **kwargs) -> str:
        """Create a cache key from arguments."""
        key_data = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
        key_hash = hashlib.md5(key_data.encode()).hexdigest()
        return f"{prefix}:{key_hash}"

    def get(self, key: str) -> Any | None:
        """Get a value from cache."""
        entry = self._cache.get(key)
        if entry is None:
            return None

        if entry.is_expired():
            del self._cache[key]
            return None

        return entry.value

    def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        """Set a value in cache."""
        # Evict if at capacity
        if len(self._cache) >= self._max_size:
            self._evict_expired()
            if len(self._cache) >= self._max_size:
                # Remove oldest entry
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]

        self._cache[key] = CacheEntry(value, ttl_seconds)

    def delete(self, key: str) -> bool:
        """Delete a value from cache."""
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def clear(self) -> None:
        """Clear all cache entries."""
        self._cache.clear()

    def _evict_expired(self) -> None:
        """Remove all expired entries."""
        expired_keys = [k for k, v in self._cache.items() if v.is_expired()]
        for key in expired_keys:
            del self._cache[key]


# Global cache instance
_cache = InMemoryCache()


def cached(prefix: str, ttl_seconds: int = 300):
    """Decorator to cache function results."""
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            # Skip cache if explicitly requested
            if kwargs.pop("skip_cache", False):
                return await func(*args, **kwargs)

            key = _cache._make_key(prefix, *args, **kwargs)

            # Try to get from cache
            cached_value = _cache.get(key)
            if cached_value is not None:
                logger.debug("Cache hit", key=key)
                return cached_value

            # Execute and cache result
            result = await func(*args, **kwargs)
            _cache.set(key, result, ttl_seconds)
            logger.debug("Cache miss, stored", key=key)

            return result

        return wrapper
    return decorator


def invalidate_cache(prefix: str, *args, **kwargs) -> bool:
    """Invalidate a specific cache entry."""
    key = _cache._make_key(prefix, *args, **kwargs)
    return _cache.delete(key)


def clear_cache() -> None:
    """Clear all cache entries."""
    _cache.clear()
```

---

### Task 5.5: Build Evaluation Framework

**packages/agent_core/src/agent_core/eval/golden_tests.py**
```python
"""Golden test framework for agent evaluation."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any
import json

from pydantic import BaseModel

from common.logging import get_logger

logger = get_logger(__name__)


class TestStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class GoldenTestCase:
    """A golden test case definition."""
    id: str
    name: str
    description: str

    # Input
    user_message: str
    tenant_id: str = "test-tenant"
    user_id: str = "test-user"
    page_context: dict[str, Any] | None = None
    selected_docs: list[str] = field(default_factory=list)

    # Expected behavior
    expected_intent: str | None = None
    expected_tools: list[str] = field(default_factory=list)  # Tools that should be called
    forbidden_tools: list[str] = field(default_factory=list)  # Tools that should NOT be called
    expected_keywords: list[str] = field(default_factory=list)  # Keywords in response
    max_tool_calls: int | None = None

    # Citation checks
    requires_citations: bool = False
    min_citations: int = 0

    # Tags for filtering
    tags: list[str] = field(default_factory=list)


@dataclass
class GoldenTestResult:
    """Result of running a golden test."""
    test_case: GoldenTestCase
    status: TestStatus
    duration_ms: float
    actual_response: str = ""
    actual_intent: str | None = None
    actual_tools_called: list[str] = field(default_factory=list)
    actual_citations: int = 0
    failures: list[str] = field(default_factory=list)
    error: str | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_id": self.test_case.id,
            "test_name": self.test_case.name,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "failures": self.failures,
            "error": self.error,
            "timestamp": self.timestamp.isoformat(),
        }


class GoldenTestRunner:
    """Runner for golden tests."""

    def __init__(self, agent_graph):
        self.agent = agent_graph
        self.results: list[GoldenTestResult] = []

    async def run_test(self, test_case: GoldenTestCase) -> GoldenTestResult:
        """Run a single golden test."""
        from datetime import datetime
        from langchain_core.messages import HumanMessage

        from agent_core.state.models import (
            AgentState,
            PageContext,
            DocumentSelection,
        )

        start_time = datetime.utcnow()
        failures = []

        try:
            # Build initial state
            page_context = None
            if test_case.page_context:
                page_context = PageContext(**test_case.page_context)

            state = AgentState(
                tenant_id=test_case.tenant_id,
                user_id=test_case.user_id,
                messages=[HumanMessage(content=test_case.user_message)],
                page_context=page_context,
                selected_docs=DocumentSelection(doc_ids=test_case.selected_docs),
            )

            # Run the agent
            config = {"configurable": {"thread_id": f"test-{test_case.id}"}}
            result = await self.agent.ainvoke(state.model_dump(), config=config)

            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000

            # Extract results
            messages = result.get("messages", [])
            actual_response = messages[-1].content if messages else ""
            actual_intent = result.get("current_intent")
            actual_tools = [tr["tool_name"] for tr in result.get("tool_results", [])]
            actual_citations = sum(
                len(tr.get("citations", []))
                for tr in result.get("tool_results", [])
            )

            # Check expectations
            if test_case.expected_intent and actual_intent != test_case.expected_intent:
                failures.append(
                    f"Intent mismatch: expected {test_case.expected_intent}, got {actual_intent}"
                )

            for expected_tool in test_case.expected_tools:
                if expected_tool not in actual_tools:
                    failures.append(f"Expected tool not called: {expected_tool}")

            for forbidden_tool in test_case.forbidden_tools:
                if forbidden_tool in actual_tools:
                    failures.append(f"Forbidden tool was called: {forbidden_tool}")

            for keyword in test_case.expected_keywords:
                if keyword.lower() not in actual_response.lower():
                    failures.append(f"Expected keyword not in response: {keyword}")

            if test_case.max_tool_calls and len(actual_tools) > test_case.max_tool_calls:
                failures.append(
                    f"Too many tool calls: {len(actual_tools)} > {test_case.max_tool_calls}"
                )

            if test_case.requires_citations and actual_citations < test_case.min_citations:
                failures.append(
                    f"Insufficient citations: {actual_citations} < {test_case.min_citations}"
                )

            status = TestStatus.PASSED if not failures else TestStatus.FAILED

            return GoldenTestResult(
                test_case=test_case,
                status=status,
                duration_ms=duration_ms,
                actual_response=actual_response,
                actual_intent=actual_intent,
                actual_tools_called=actual_tools,
                actual_citations=actual_citations,
                failures=failures,
            )

        except Exception as e:
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            logger.error("Golden test error", test_id=test_case.id, error=str(e))

            return GoldenTestResult(
                test_case=test_case,
                status=TestStatus.ERROR,
                duration_ms=duration_ms,
                error=str(e),
            )

    async def run_suite(
        self,
        test_cases: list[GoldenTestCase],
        tags: list[str] | None = None,
    ) -> list[GoldenTestResult]:
        """Run a suite of golden tests."""
        # Filter by tags if provided
        if tags:
            test_cases = [tc for tc in test_cases if any(t in tc.tags for t in tags)]

        results = []
        for test_case in test_cases:
            logger.info("Running golden test", test_id=test_case.id, name=test_case.name)
            result = await self.run_test(test_case)
            results.append(result)
            self.results.append(result)

        return results

    def get_summary(self) -> dict[str, Any]:
        """Get summary of test results."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.status == TestStatus.PASSED)
        failed = sum(1 for r in self.results if r.status == TestStatus.FAILED)
        errors = sum(1 for r in self.results if r.status == TestStatus.ERROR)

        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "errors": errors,
            "pass_rate": passed / total if total > 0 else 0,
            "avg_duration_ms": sum(r.duration_ms for r in self.results) / total if total > 0 else 0,
        }


# Sample test cases
SAMPLE_GOLDEN_TESTS = [
    GoldenTestCase(
        id="qa-basic-001",
        name="Basic Q&A",
        description="Simple question about an opportunity",
        user_message="What is this opportunity about?",
        page_context={"module_id": "deals", "entity_type": "opportunity", "entity_id": "opp-001"},
        expected_intent="qa",
        expected_tools=["mcp:opportunities:get_opportunity"],
        tags=["qa", "deals", "basic"],
    ),
    GoldenTestCase(
        id="gen-memo-001",
        name="Generate Investment Memo",
        description="Request to generate an investment memo",
        user_message="Generate an investment memo for this opportunity",
        page_context={"module_id": "deals", "entity_type": "opportunity", "entity_id": "opp-001"},
        expected_intent="generate",
        requires_citations=True,
        min_citations=1,
        tags=["generate", "deals", "memo"],
    ),
]
```

---

### Task 5.6: Create Health Check Endpoints

**apps/agent_api/src/agent_api/api/health.py**
```python
"""Health check endpoints."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from common.config import get_settings
from common.logging import get_logger

logger = get_logger(__name__)
settings = get_settings()

router = APIRouter(tags=["health"])


class HealthStatus(BaseModel):
    """Health check response."""
    status: str
    version: str
    environment: str
    timestamp: str
    checks: dict[str, dict[str, Any]]


class DependencyCheck:
    """Check a dependency's health."""

    @staticmethod
    async def check_cosmos() -> dict[str, Any]:
        """Check Cosmos DB connectivity."""
        try:
            from azure.cosmos import CosmosClient

            client = CosmosClient(settings.cosmos_endpoint, credential=settings.cosmos_key)
            # Simple operation to verify connection
            list(client.list_databases())

            return {"status": "healthy", "latency_ms": 0}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}

    @staticmethod
    async def check_openai() -> dict[str, Any]:
        """Check Azure OpenAI connectivity."""
        try:
            from langchain_openai import AzureChatOpenAI

            llm = AzureChatOpenAI(
                azure_endpoint=settings.azure_openai_endpoint,
                api_key=settings.azure_openai_api_key,
                api_version=settings.azure_openai_api_version,
                deployment_name=settings.azure_openai_deployment_name,
            )
            # Simple completion to verify
            await llm.ainvoke([{"role": "user", "content": "ping"}])

            return {"status": "healthy"}
        except Exception as e:
            return {"status": "unhealthy", "error": str(e)}


@router.get("/health", response_model=HealthStatus)
async def health_check() -> HealthStatus:
    """Comprehensive health check."""
    checks = {
        "cosmos": await DependencyCheck.check_cosmos(),
        "openai": await DependencyCheck.check_openai(),
    }

    overall_status = "healthy" if all(
        c["status"] == "healthy" for c in checks.values()
    ) else "degraded"

    return HealthStatus(
        status=overall_status,
        version="0.1.0",
        environment=settings.environment,
        timestamp=datetime.utcnow().isoformat(),
        checks=checks,
    )


@router.get("/health/live")
async def liveness_check():
    """Kubernetes liveness probe."""
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness_check():
    """Kubernetes readiness probe."""
    # Check if essential services are available
    cosmos_check = await DependencyCheck.check_cosmos()

    if cosmos_check["status"] != "healthy":
        return {"status": "not_ready", "reason": "Cosmos DB unavailable"}

    return {"status": "ready"}
```

---

### Task 5.7: Create Runbooks

**docs/runbooks.md**
```markdown
# Operational Runbooks

## 1. Startup Procedure

### Agent API
```bash
# Start the agent API
uvicorn apps.agent_api.src.agent_api.main:app --host 0.0.0.0 --port 8000

# With multiple workers (production)
uvicorn apps.agent_api.src.agent_api.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### MCP Servers
```bash
# Start each MCP server
python -m apps.mcp_servers.opportunities.src.mcp_opportunities.server
python -m apps.mcp_servers.clients.src.mcp_clients.server
python -m apps.mcp_servers.risk_planning.src.mcp_risk_planning.server
python -m apps.mcp_servers.reporting.src.mcp_reporting.server
python -m apps.mcp_servers.admin_policy.src.mcp_admin_policy.server
```

## 2. Health Checks

### Check API Health
```bash
# Liveness
curl http://localhost:8000/health/live

# Readiness
curl http://localhost:8000/health/ready

# Full health check
curl http://localhost:8000/health
```

### Check MCP Server Health
```bash
# List tools (confirms server is responding)
curl -X POST http://localhost:8001/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","params":{},"id":1}'
```

## 3. Common Issues

### Circuit Breaker Open

**Symptoms:**
- Errors with "Circuit breaker is open"
- Requests failing fast

**Resolution:**
1. Check the failing dependency (logs will show which)
2. Verify the dependency is healthy
3. Wait for the circuit breaker timeout (default 30s)
4. Or restart the service to reset breakers

### High Memory Usage

**Symptoms:**
- OOM errors
- Slow responses

**Resolution:**
1. Check in-memory cache size
2. Clear cache if needed: `POST /admin/cache/clear`
3. Check for memory leaks in session state
4. Consider scaling horizontally

### Cosmos DB Throttling

**Symptoms:**
- 429 errors from Cosmos DB
- Slow checkpoint saves

**Resolution:**
1. Check RU consumption in Azure portal
2. Scale up throughput temporarily
3. Enable autoscale if not already
4. Review query patterns for optimization

## 4. Debugging

### Enable Debug Logging
```bash
export LOG_LEVEL=DEBUG
```

### View Session State
```bash
curl "http://localhost:8000/v1/sessions/{session_id}?tenant_id={tenant_id}"
```

### Trace a Request
1. Check App Insights for the request trace
2. Filter by operation_id or session_id
3. Review span durations to identify bottlenecks

## 5. Scaling

### Horizontal Scaling
```bash
# Azure Container Apps
az containerapp update \
  --name agent-api \
  --resource-group <rg> \
  --min-replicas 2 \
  --max-replicas 10
```

### Cosmos DB Scaling
```bash
# Increase throughput
az cosmosdb sql container throughput update \
  --account-name <account> \
  --resource-group <rg> \
  --database-name invictus-copilot \
  --name sessions \
  --throughput 1000
```

## 6. Disaster Recovery

### Backup Verification
1. Verify Cosmos DB continuous backup is enabled
2. Test point-in-time restore in non-prod

### Restore from Backup
```bash
# Restore Cosmos DB to point in time
az cosmosdb sql restorable-database list \
  --location <location> \
  --instance-id <instance-id>

az cosmosdb restore \
  --target-database-account-name <new-account> \
  --account-name <source-account> \
  --restore-timestamp <timestamp>
```

## 7. Security Incident Response

### Suspected Data Breach
1. Rotate all API keys immediately
2. Review audit logs for suspicious activity
3. Check for unauthorized session access
4. Notify security team

### Key Rotation
```bash
# Regenerate Cosmos DB keys
az cosmosdb keys regenerate \
  --name <account> \
  --resource-group <rg> \
  --key-kind primary

# Update Key Vault
az keyvault secret set \
  --vault-name <vault> \
  --name cosmos-key \
  --value <new-key>

# Restart services to pick up new key
```
```

---

## Azure Configuration Checklist

### 1. Set Up App Insights

```bash
# Create App Insights
az monitor app-insights component create \
  --app invictus-copilot \
  --location <location> \
  --resource-group <rg> \
  --kind web

# Get connection string
az monitor app-insights component show \
  --app invictus-copilot \
  --resource-group <rg> \
  --query connectionString
```

### 2. Configure Container Apps

```bash
# Create Container App environment
az containerapp env create \
  --name invictus-env \
  --resource-group <rg> \
  --location <location>

# Deploy agent-api
az containerapp create \
  --name agent-api \
  --resource-group <rg> \
  --environment invictus-env \
  --image <registry>/agent-api:latest \
  --target-port 8000 \
  --ingress external \
  --min-replicas 2 \
  --max-replicas 10 \
  --env-vars \
    APPLICATIONINSIGHTS_CONNECTION_STRING=<connection-string> \
    COSMOS_ENDPOINT=<endpoint> \
    COSMOS_KEY=secretref:cosmos-key
```

### 3. Set Up Alerts

```bash
# High error rate alert
az monitor metrics alert create \
  --name high-error-rate \
  --resource-group <rg> \
  --scopes <app-insights-resource-id> \
  --condition "count requests/failed > 10" \
  --window-size 5m \
  --evaluation-frequency 1m

# High latency alert
az monitor metrics alert create \
  --name high-latency \
  --resource-group <rg> \
  --scopes <app-insights-resource-id> \
  --condition "avg requests/duration > 5000" \
  --window-size 5m
```

---

## Testing Checklist

### Performance Tests

- [ ] Load test with 100 concurrent users
- [ ] Verify response times under load
- [ ] Test circuit breaker behavior
- [ ] Verify cache effectiveness

### Resilience Tests

- [ ] Kill a database connection, verify recovery
- [ ] Simulate network latency
- [ ] Test with Cosmos DB throttling
- [ ] Verify graceful degradation

### Golden Tests

- [ ] All basic Q&A tests pass
- [ ] All generation tests pass
- [ ] Citation checks pass
- [ ] Tool usage matches expectations

---

## Expected Deliverables

After completing Phase 5:

1. **Observability**:
   - OpenTelemetry integration
   - Custom metrics (tool calls, HITL, artifacts, errors)
   - App Insights dashboards
   - Alerts for critical conditions

2. **Reliability**:
   - Retry logic with exponential backoff
   - Circuit breakers for external dependencies
   - Response caching
   - Graceful degradation

3. **Evaluation**:
   - Golden test framework
   - Sample test cases
   - CI integration for golden tests

4. **Operations**:
   - Health check endpoints (live, ready, full)
   - Runbooks for common scenarios
   - Disaster recovery procedures

5. **Documentation**:
   - Architecture documentation
   - API documentation
   - Security documentation
   - Operational runbooks

---

## Security Upgrade Path

For future security enhancements:

### 1. Replace Password Auth with Managed Identity

```python
# Current (password-based)
from azure.cosmos import CosmosClient
client = CosmosClient(endpoint, credential=key)

# Future (Managed Identity)
from azure.identity import DefaultAzureCredential
credential = DefaultAzureCredential()
client = CosmosClient(endpoint, credential=credential)
```

### 2. Enable Entra ID for Users

- Integrate with Azure AD for user authentication
- Use access tokens instead of simple user_id
- Implement proper RBAC

### 3. Enable Private Networking

- Deploy to VNet-integrated Container Apps
- Use Private Endpoints for Cosmos DB
- Enable Private Link for all Azure services

---

## Conclusion

After completing all phases, you will have a production-ready AI Copilot Agent Platform with:

- **Core Functionality**: Q&A, content generation, document retrieval
- **Multi-Module Support**: Works across Deals, CRM, Risk, Admin
- **HITL & Governance**: Safe, controlled AI behavior
- **Observability**: Full visibility into agent behavior
- **Reliability**: Resilient to failures
- **Scalability**: Ready for production load

The platform can now be deployed to production and iteratively improved based on user feedback and operational experience.
