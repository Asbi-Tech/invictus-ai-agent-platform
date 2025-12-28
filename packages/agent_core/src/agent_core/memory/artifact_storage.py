"""Artifact storage for CosmosDB persistence."""

from datetime import datetime
from typing import Any

from azure.cosmos import CosmosClient
from azure.cosmos.exceptions import CosmosResourceNotFoundError

from common.logging import get_logger

logger = get_logger(__name__)


class ArtifactStorage:
    """
    Store and retrieve artifacts from CosmosDB.

    Uses tenant_id as the partition key for efficient multi-tenant queries.
    Document ID pattern: {tenant_id}:{artifact_id}
    """

    def __init__(
        self,
        endpoint: str,
        key: str,
        database_name: str,
        container_name: str = "artifacts",
    ):
        """
        Initialize the Artifact storage.

        Args:
            endpoint: Cosmos DB endpoint URL
            key: Cosmos DB primary key
            database_name: Name of the database
            container_name: Name of the container (default: "artifacts")
        """
        self.client = CosmosClient(endpoint, credential=key)
        self.database = self.client.get_database_client(database_name)
        self.container = self.database.get_container_client(container_name)
        logger.info(
            "Initialized ArtifactStorage",
            database=database_name,
            container=container_name,
        )

    def _make_id(self, tenant_id: str, artifact_id: str) -> str:
        """Create a unique document ID."""
        return f"{tenant_id}:{artifact_id}"

    def save_artifact(
        self,
        tenant_id: str,
        session_id: str,
        artifact: dict[str, Any],
    ) -> dict:
        """
        Save artifact to CosmosDB.

        Args:
            tenant_id: Tenant ID (partition key)
            session_id: Session ID that created this artifact
            artifact: Artifact data with artifact_id, content, etc.

        Returns:
            The saved item from Cosmos
        """
        artifact_id = artifact.get("artifact_id")
        if not artifact_id:
            raise ValueError("artifact_id is required")

        doc_id = self._make_id(tenant_id, artifact_id)

        item = {
            "id": doc_id,
            "tenant_id": tenant_id,
            "session_id": session_id,
            "artifact_id": artifact_id,
            "artifact_type": artifact.get("artifact_type"),
            "title": artifact.get("title"),
            "content": artifact.get("content"),
            "version": artifact.get("version", 1),
            "citations": artifact.get("citations", []),
            "metadata": artifact.get("metadata", {}),
            "created_at": artifact.get("created_at", datetime.utcnow().isoformat()),
            "updated_at": datetime.utcnow().isoformat(),
        }

        result = self.container.upsert_item(item)

        logger.info(
            "Saved artifact",
            artifact_id=artifact_id,
            tenant_id=tenant_id,
            session_id=session_id,
        )

        return result

    def get_artifact(
        self,
        tenant_id: str,
        artifact_id: str,
    ) -> dict | None:
        """
        Retrieve artifact by ID.

        Args:
            tenant_id: Tenant ID (partition key)
            artifact_id: Artifact ID

        Returns:
            Artifact dict if found, None otherwise
        """
        try:
            doc_id = self._make_id(tenant_id, artifact_id)
            item = self.container.read_item(item=doc_id, partition_key=tenant_id)

            logger.debug("Retrieved artifact", artifact_id=artifact_id)
            return item

        except CosmosResourceNotFoundError:
            logger.debug("Artifact not found", artifact_id=artifact_id)
            return None
        except Exception as e:
            logger.warning(
                "Error retrieving artifact",
                artifact_id=artifact_id,
                error=str(e),
            )
            return None

    def get_session_artifacts(
        self,
        tenant_id: str,
        session_id: str,
    ) -> list[dict]:
        """
        Get all artifacts for a session.

        Args:
            tenant_id: Tenant ID (partition key)
            session_id: Session ID

        Returns:
            List of artifact dicts, ordered by created_at desc
        """
        query = """
            SELECT * FROM c
            WHERE c.session_id = @session_id
            ORDER BY c.created_at DESC
        """

        items = list(
            self.container.query_items(
                query=query,
                parameters=[{"name": "@session_id", "value": session_id}],
                partition_key=tenant_id,
            )
        )

        logger.debug(
            "Retrieved session artifacts",
            session_id=session_id,
            count=len(items),
        )

        return items

    def update_artifact(
        self,
        tenant_id: str,
        artifact_id: str,
        updates: dict[str, Any],
    ) -> dict | None:
        """
        Update artifact content/metadata.

        Increments version and updates the updated_at timestamp.

        Args:
            tenant_id: Tenant ID (partition key)
            artifact_id: Artifact ID
            updates: Dict of fields to update

        Returns:
            Updated artifact dict, or None if not found
        """
        existing = self.get_artifact(tenant_id, artifact_id)
        if not existing:
            logger.warning("Artifact not found for update", artifact_id=artifact_id)
            return None

        # Increment version
        existing["version"] = existing.get("version", 1) + 1
        existing["updated_at"] = datetime.utcnow().isoformat()

        # Apply updates (protect certain fields from modification)
        protected_fields = {"id", "tenant_id", "artifact_id", "created_at"}
        for key, value in updates.items():
            if key not in protected_fields:
                existing[key] = value

        result = self.container.upsert_item(existing)

        logger.info(
            "Updated artifact",
            artifact_id=artifact_id,
            version=existing["version"],
        )

        return result

    def delete_artifact(
        self,
        tenant_id: str,
        artifact_id: str,
    ) -> bool:
        """
        Delete an artifact.

        Args:
            tenant_id: Tenant ID (partition key)
            artifact_id: Artifact ID

        Returns:
            True if deleted, False if not found
        """
        try:
            doc_id = self._make_id(tenant_id, artifact_id)
            self.container.delete_item(item=doc_id, partition_key=tenant_id)

            logger.info("Deleted artifact", artifact_id=artifact_id)
            return True

        except CosmosResourceNotFoundError:
            logger.debug("Artifact not found for deletion", artifact_id=artifact_id)
            return False
        except Exception as e:
            logger.error(
                "Error deleting artifact",
                artifact_id=artifact_id,
                error=str(e),
            )
            raise

    # ============================================================
    # Async methods (wrappers for sync methods)
    # ============================================================

    async def asave_artifact(
        self,
        tenant_id: str,
        session_id: str,
        artifact: dict[str, Any],
    ) -> dict:
        """Async version of save_artifact."""
        return self.save_artifact(tenant_id, session_id, artifact)

    async def aget_artifact(
        self,
        tenant_id: str,
        artifact_id: str,
    ) -> dict | None:
        """Async version of get_artifact."""
        return self.get_artifact(tenant_id, artifact_id)

    async def aget_session_artifacts(
        self,
        tenant_id: str,
        session_id: str,
    ) -> list[dict]:
        """Async version of get_session_artifacts."""
        return self.get_session_artifacts(tenant_id, session_id)

    async def aupdate_artifact(
        self,
        tenant_id: str,
        artifact_id: str,
        updates: dict[str, Any],
    ) -> dict | None:
        """Async version of update_artifact."""
        return self.update_artifact(tenant_id, artifact_id, updates)

    async def adelete_artifact(
        self,
        tenant_id: str,
        artifact_id: str,
    ) -> bool:
        """Async version of delete_artifact."""
        return self.delete_artifact(tenant_id, artifact_id)
