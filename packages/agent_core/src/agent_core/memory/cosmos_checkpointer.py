"""Cosmos DB checkpointer for LangGraph state persistence."""

import json
from datetime import datetime
from typing import Any, AsyncIterator, Iterator, Optional, Sequence, Tuple

from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langchain_core.runnables import RunnableConfig

from common.logging import get_logger

logger = get_logger(__name__)


class CosmosDBCheckpointer(BaseCheckpointSaver):
    """
    Checkpointer that persists LangGraph state to Cosmos DB.

    Uses thread_id as the partition key for efficient queries within a session.
    """

    def __init__(
        self,
        endpoint: str,
        key: str,
        database_name: str,
        container_name: str = "checkpoints",
    ):
        """
        Initialize the Cosmos DB checkpointer.

        Args:
            endpoint: Cosmos DB endpoint URL
            key: Cosmos DB primary key
            database_name: Name of the database
            container_name: Name of the container (default: "checkpoints")
        """
        super().__init__()
        self.client = CosmosClient(endpoint, credential=key)
        self.database = self.client.get_database_client(database_name)
        self.container = self.database.get_container_client(container_name)
        logger.info(
            "Initialized Cosmos DB checkpointer",
            database=database_name,
            container=container_name,
        )

    def _make_id(self, thread_id: str, checkpoint_ns: str, checkpoint_id: str) -> str:
        """Create a unique document ID."""
        return f"{thread_id}:{checkpoint_ns}:{checkpoint_id}"

    def get_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        """
        Get a checkpoint tuple by config.

        Args:
            config: The runnable config containing thread_id and optional checkpoint_id

        Returns:
            CheckpointTuple if found, None otherwise
        """
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = config["configurable"].get("checkpoint_id")

        try:
            if checkpoint_id:
                # Get specific checkpoint
                doc_id = self._make_id(thread_id, checkpoint_ns, checkpoint_id)
                item = self.container.read_item(item=doc_id, partition_key=thread_id)
            else:
                # Get latest checkpoint for thread
                query = """
                    SELECT TOP 1 * FROM c
                    WHERE c.thread_id = @thread_id
                    AND c.checkpoint_ns = @checkpoint_ns
                    ORDER BY c.created_at DESC
                """
                items = list(
                    self.container.query_items(
                        query=query,
                        parameters=[
                            {"name": "@thread_id", "value": thread_id},
                            {"name": "@checkpoint_ns", "value": checkpoint_ns},
                        ],
                        partition_key=thread_id,
                    )
                )
                if not items:
                    return None
                item = items[0]

            return CheckpointTuple(
                config=config,
                checkpoint=json.loads(item["checkpoint"]),
                metadata=json.loads(item.get("metadata", "{}")),
                parent_config=(
                    json.loads(item["parent_config"]) if item.get("parent_config") else None
                ),
            )
        except CosmosResourceNotFoundError:
            return None
        except Exception as e:
            logger.error("Failed to get checkpoint", error=str(e), thread_id=thread_id)
            raise

    def list(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> Iterator[CheckpointTuple]:
        """
        List checkpoints for a thread.

        Args:
            config: Config containing thread_id
            filter: Optional filter criteria
            before: Optional config to get checkpoints before
            limit: Maximum number of checkpoints to return

        Yields:
            CheckpointTuple for each matching checkpoint
        """
        if not config:
            return

        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")

        query = """
            SELECT * FROM c
            WHERE c.thread_id = @thread_id
            AND c.checkpoint_ns = @checkpoint_ns
            ORDER BY c.created_at DESC
        """
        params = [
            {"name": "@thread_id", "value": thread_id},
            {"name": "@checkpoint_ns", "value": checkpoint_ns},
        ]

        items = self.container.query_items(
            query=query,
            parameters=params,
            partition_key=thread_id,
            max_item_count=limit or 100,
        )

        for item in items:
            yield CheckpointTuple(
                config={
                    "configurable": {
                        "thread_id": thread_id,
                        "checkpoint_ns": checkpoint_ns,
                        "checkpoint_id": item["checkpoint_id"],
                    }
                },
                checkpoint=json.loads(item["checkpoint"]),
                metadata=json.loads(item.get("metadata", "{}")),
                parent_config=(
                    json.loads(item["parent_config"]) if item.get("parent_config") else None
                ),
            )

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict[str, Any],
    ) -> RunnableConfig:
        """
        Save a checkpoint.

        Args:
            config: The runnable config
            checkpoint: The checkpoint data to save
            metadata: Checkpoint metadata
            new_versions: Version information for channels

        Returns:
            Updated config with checkpoint_id
        """
        thread_id = config["configurable"]["thread_id"]
        checkpoint_ns = config["configurable"].get("checkpoint_ns", "")
        checkpoint_id = checkpoint["id"]
        parent_config = config["configurable"].get("parent_config")

        doc_id = self._make_id(thread_id, checkpoint_ns, checkpoint_id)

        item = {
            "id": doc_id,
            "thread_id": thread_id,
            "checkpoint_ns": checkpoint_ns,
            "checkpoint_id": checkpoint_id,
            "checkpoint": json.dumps(checkpoint, default=str),
            "metadata": json.dumps(metadata, default=str),
            "parent_config": json.dumps(parent_config, default=str) if parent_config else None,
            "created_at": datetime.utcnow().isoformat(),
        }

        self.container.upsert_item(item)

        logger.debug(
            "Saved checkpoint",
            thread_id=thread_id,
            checkpoint_id=checkpoint_id,
        )

        return {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": checkpoint_ns,
                "checkpoint_id": checkpoint_id,
            }
        }

    def put_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[Tuple[str, Any]],
        task_id: str,
    ) -> None:
        """
        Save intermediate writes for pending tasks.

        For MVP, this is a no-op. Full implementation needed for
        advanced interrupt/resume scenarios.

        Args:
            config: The runnable config
            writes: Sequence of (channel, value) tuples
            task_id: The task identifier
        """
        # For MVP, we don't implement pending writes storage
        # This is needed for more advanced interrupt/resume scenarios
        pass

    # ============================================================
    # Async methods required by LangGraph
    # ============================================================

    async def aget_tuple(self, config: RunnableConfig) -> Optional[CheckpointTuple]:
        """Async version of get_tuple."""
        # Use sync method since azure-cosmos SDK is sync
        return self.get_tuple(config)

    async def aput(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: dict[str, Any],
    ) -> RunnableConfig:
        """Async version of put."""
        return self.put(config, checkpoint, metadata, new_versions)

    async def alist(
        self,
        config: Optional[RunnableConfig],
        *,
        filter: Optional[dict[str, Any]] = None,
        before: Optional[RunnableConfig] = None,
        limit: Optional[int] = None,
    ) -> AsyncIterator[CheckpointTuple]:
        """Async version of list."""
        for item in self.list(config, filter=filter, before=before, limit=limit):
            yield item

    async def aput_writes(
        self,
        config: RunnableConfig,
        writes: Sequence[Tuple[str, Any]],
        task_id: str,
    ) -> None:
        """Async version of put_writes."""
        self.put_writes(config, writes, task_id)

    def delete_thread(self, thread_id: str) -> None:
        """
        Delete all checkpoints for a thread.

        Args:
            thread_id: The thread ID to delete checkpoints for
        """
        query = "SELECT c.id FROM c WHERE c.thread_id = @thread_id"
        items = self.container.query_items(
            query=query,
            parameters=[{"name": "@thread_id", "value": thread_id}],
            partition_key=thread_id,
        )

        for item in items:
            self.container.delete_item(item=item["id"], partition_key=thread_id)

        logger.info("Deleted thread checkpoints", thread_id=thread_id)
