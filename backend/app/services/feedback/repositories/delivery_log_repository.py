from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.app.core.database import get_connection
from backend.app.shared.models import DeliveryLog


class SQLiteDeliveryLogRepository:
    def __init__(self, database_path: Path, timezone_offset: str = "+08:00") -> None:
        self.database_path = database_path
        self._timezone_offset = timezone_offset

    async def save(self, log: DeliveryLog) -> None:
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO delivery_logs (
                    log_id,
                    task_id,
                    decision_id,
                    event_id,
                    user_id,
                    channel,
                    status,
                    retry_count,
                    provider_message_id,
                    error_message,
                    delivered_at,
                    metadata_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    log.log_id,
                    log.task_id,
                    log.decision_id,
                    log.event_id,
                    log.user_id,
                    log.channel,
                    log.status,
                    log.retry_count,
                    log.provider_message_id,
                    log.error_message,
                    log.delivered_at,
                    json.dumps(log.metadata, ensure_ascii=False),
                    log.delivered_at or self._default_timestamp(),
                ),
            )
            connection.commit()

    async def get_by_log_id(self, log_id: str) -> DeliveryLog | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM delivery_logs WHERE log_id = ? LIMIT 1",
                (log_id,),
            ).fetchone()
        return self._row_to_log(row) if row else None

    async def get_latest_by_event_and_user(self, event_id: str, user_id: str) -> DeliveryLog | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT * FROM delivery_logs
                WHERE event_id = ? AND user_id = ?
                ORDER BY COALESCE(delivered_at, created_at) DESC
                LIMIT 1
                """,
                (event_id, user_id),
            ).fetchone()
        return self._row_to_log(row) if row else None

    @staticmethod
    def _row_to_log(row) -> DeliveryLog:
        return DeliveryLog.model_validate(
            {
                "log_id": row["log_id"],
                "task_id": row["task_id"],
                "decision_id": row["decision_id"],
                "event_id": row["event_id"],
                "user_id": row["user_id"],
                "channel": row["channel"],
                "status": row["status"],
                "retry_count": row["retry_count"],
                "provider_message_id": row["provider_message_id"],
                "error_message": row["error_message"],
                "delivered_at": row["delivered_at"],
                "metadata": json.loads(row["metadata_json"]),
            }
        )

    def _default_timestamp(self) -> str:
        offset = self._parse_timezone_offset(self._timezone_offset)
        return datetime.now(timezone.utc).astimezone(offset).isoformat()

    @staticmethod
    def _parse_timezone_offset(value: str) -> timezone:
        sign = 1 if value.startswith("+") else -1
        hour_text, minute_text = value[1:].split(":", maxsplit=1)
        delta = timedelta(hours=int(hour_text), minutes=int(minute_text))
        return timezone(sign * delta)
