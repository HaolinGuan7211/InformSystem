from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from backend.app.core.database import get_connection
from backend.app.shared.models import DeliveryLog


class DeliveryLogRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    async def save(self, log: DeliveryLog, created_at: str | None = None) -> None:
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO delivery_logs (
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
                self._log_to_row(log, created_at),
            )
            connection.commit()

    async def get_by_log_id(self, log_id: str) -> DeliveryLog | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM delivery_logs
                WHERE log_id = ?
                LIMIT 1
                """,
                (log_id,),
            ).fetchone()
        return self._row_to_log(row) if row else None

    async def save_many(self, logs: list[DeliveryLog], created_at: str | None = None) -> None:
        if not logs:
            return
        with get_connection(self.database_path) as connection:
            connection.executemany(
                """
                INSERT INTO delivery_logs (
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
                [self._log_to_row(log, created_at) for log in logs],
            )
            connection.commit()

    async def get_latest_by_task(self, task_id: str) -> DeliveryLog | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM delivery_logs
                WHERE task_id = ?
                ORDER BY COALESCE(delivered_at, created_at) DESC, created_at DESC, rowid DESC
                LIMIT 1
                """,
                (task_id,),
            ).fetchone()
        return self._row_to_log(row) if row else None

    async def get_latest_by_event_and_user(
        self,
        event_id: str,
        user_id: str,
    ) -> DeliveryLog | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM delivery_logs
                WHERE event_id = ? AND user_id = ?
                ORDER BY COALESCE(delivered_at, created_at) DESC, created_at DESC, rowid DESC
                LIMIT 1
                """,
                (event_id, user_id),
            ).fetchone()
        return self._row_to_log(row) if row else None

    async def get_latest_terminal_log(self, task_id: str) -> DeliveryLog | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM delivery_logs
                WHERE task_id = ? AND status IN ('sent', 'skipped')
                ORDER BY COALESCE(delivered_at, created_at) DESC, created_at DESC, rowid DESC
                LIMIT 1
                """,
                (task_id,),
            ).fetchone()
        return self._row_to_log(row) if row else None

    async def list_by_task(self, task_id: str) -> list[DeliveryLog]:
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM delivery_logs
                WHERE task_id = ?
                ORDER BY created_at ASC, rowid ASC
                """,
                (task_id,),
            ).fetchall()
        return [self._row_to_log(row) for row in rows]

    async def list_by_user(self, user_id: str, limit: int = 100) -> list[DeliveryLog]:
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM delivery_logs
                WHERE user_id = ?
                ORDER BY COALESCE(delivered_at, created_at) DESC, created_at DESC, rowid DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [self._row_to_log(row) for row in rows]

    def _log_to_row(self, log: DeliveryLog, created_at: str | None) -> tuple[object, ...]:
        return (
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
            created_at or log.delivered_at or datetime.now(timezone.utc).isoformat(),
        )

    def _row_to_log(self, row) -> DeliveryLog:
        return DeliveryLog.model_validate(
            {
                "log_id": row["log_id"],
                "task_id": row["task_id"],
                "decision_id": row["decision_id"],
                "event_id": row["event_id"],
                "user_id": row["user_id"],
                "channel": row["channel"],
                "status": row["status"],
                "retry_count": int(row["retry_count"]),
                "provider_message_id": row["provider_message_id"],
                "error_message": row["error_message"],
                "delivered_at": row["delivered_at"],
                "metadata": json.loads(row["metadata_json"]),
            }
        )
