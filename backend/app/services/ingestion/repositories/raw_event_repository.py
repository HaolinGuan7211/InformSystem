from __future__ import annotations

import json
from pathlib import Path

from backend.app.core.database import get_connection
from backend.app.services.ingestion.models import SourceEvent


class RawEventRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    async def save_events(self, events: list[SourceEvent]) -> None:
        if not events:
            return

        with get_connection(self.database_path) as connection:
            connection.executemany(
                """
                INSERT OR REPLACE INTO raw_events (
                    event_id,
                    source_id,
                    source_type,
                    source_name,
                    channel_type,
                    title,
                    content_text,
                    content_html,
                    author,
                    published_at,
                    collected_at,
                    url,
                    attachments_json,
                    metadata_json,
                    canonical_notice_id,
                    content_hash,
                    unique_source_key
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [self._event_to_row(event) for event in events],
            )
            connection.commit()

    async def get_event_by_id(self, event_id: str) -> SourceEvent | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM raw_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return self._row_to_event(row) if row else None

    async def list_events(self, limit: int = 100) -> list[SourceEvent]:
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                "SELECT * FROM raw_events ORDER BY collected_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    async def find_by_unique_source_key(self, unique_source_key: str) -> SourceEvent | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM raw_events WHERE unique_source_key = ? LIMIT 1",
                (unique_source_key,),
            ).fetchone()
        return self._row_to_event(row) if row else None

    async def find_by_url(self, url: str) -> SourceEvent | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM raw_events WHERE url = ? LIMIT 1",
                (url,),
            ).fetchone()
        return self._row_to_event(row) if row else None

    async def find_by_content_hash(self, content_hash: str) -> SourceEvent | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM raw_events WHERE content_hash = ? LIMIT 1",
                (content_hash,),
            ).fetchone()
        return self._row_to_event(row) if row else None

    def _event_to_row(self, event: SourceEvent) -> tuple[str | None, ...]:
        metadata = dict(event.metadata)
        return (
            event.event_id,
            event.source_id,
            event.source_type,
            event.source_name,
            event.channel_type,
            event.title,
            event.content_text,
            event.content_html,
            event.author,
            event.published_at,
            event.collected_at,
            event.url,
            json.dumps([attachment.model_dump() for attachment in event.attachments], ensure_ascii=False),
            json.dumps(metadata, ensure_ascii=False),
            metadata.get("canonical_notice_id"),
            metadata.get("content_hash"),
            metadata.get("unique_source_key"),
        )

    def _row_to_event(self, row) -> SourceEvent:
        return SourceEvent(
            event_id=row["event_id"],
            source_id=row["source_id"],
            source_type=row["source_type"],
            source_name=row["source_name"],
            channel_type=row["channel_type"],
            title=row["title"],
            content_text=row["content_text"],
            content_html=row["content_html"],
            author=row["author"],
            published_at=row["published_at"],
            collected_at=row["collected_at"],
            url=row["url"],
            attachments=json.loads(row["attachments_json"]),
            metadata=json.loads(row["metadata_json"]),
        )

