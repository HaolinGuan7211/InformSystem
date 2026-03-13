from __future__ import annotations

import hashlib

from backend.app.services.ingestion.models import SourceEvent
from backend.app.services.ingestion.repositories.raw_event_repository import RawEventRepository


class Deduplicator:
    def __init__(self, raw_event_repository: RawEventRepository) -> None:
        self._raw_event_repository = raw_event_repository

    async def is_duplicate(self, event: SourceEvent) -> bool:
        self._enrich_metadata(event)
        if unique_source_key := event.metadata.get("unique_source_key"):
            if await self._raw_event_repository.find_by_unique_source_key(unique_source_key):
                return True

        if event.url:
            if await self._raw_event_repository.find_by_url(event.url):
                return True

        if content_hash := event.metadata.get("content_hash"):
            if await self._raw_event_repository.find_by_content_hash(content_hash):
                return True

        return False

    async def assign_canonical_id(self, event: SourceEvent) -> str:
        self._enrich_metadata(event)
        existing = None
        if unique_source_key := event.metadata.get("unique_source_key"):
            existing = await self._raw_event_repository.find_by_unique_source_key(unique_source_key)
        if existing is None and event.url:
            existing = await self._raw_event_repository.find_by_url(event.url)
        if existing is None and (content_hash := event.metadata.get("content_hash")):
            existing = await self._raw_event_repository.find_by_content_hash(content_hash)

        canonical_notice_id = (
            existing.metadata.get("canonical_notice_id") if existing else None
        ) or f"notice_{event.metadata['content_hash'][:16]}"
        event.metadata["canonical_notice_id"] = canonical_notice_id
        return canonical_notice_id

    def _enrich_metadata(self, event: SourceEvent) -> None:
        if "unique_source_key" not in event.metadata and event.url:
            event.metadata["unique_source_key"] = f"{event.source_id}:{event.url}"
        if "content_hash" not in event.metadata:
            basis = "|".join(
                [
                    event.title or "",
                    event.content_text,
                    event.published_at or "",
                ]
            )
            event.metadata["content_hash"] = hashlib.sha256(basis.encode("utf-8")).hexdigest()

