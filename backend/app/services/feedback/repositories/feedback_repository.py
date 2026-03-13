from __future__ import annotations

import json
from pathlib import Path

from backend.app.core.database import get_connection
from backend.app.shared.models import UserFeedbackRecord


class SQLiteFeedbackRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    async def save(self, record: UserFeedbackRecord) -> None:
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO user_feedback (
                    feedback_id,
                    user_id,
                    event_id,
                    decision_id,
                    delivery_log_id,
                    feedback_type,
                    rating,
                    comment,
                    metadata_json,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.feedback_id,
                    record.user_id,
                    record.event_id,
                    record.decision_id,
                    record.delivery_log_id,
                    record.feedback_type,
                    record.rating,
                    record.comment,
                    json.dumps(record.metadata, ensure_ascii=False),
                    record.created_at,
                ),
            )
            connection.commit()

    async def get_by_feedback_id(self, feedback_id: str) -> UserFeedbackRecord | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM user_feedback WHERE feedback_id = ? LIMIT 1",
                (feedback_id,),
            ).fetchone()
        return self._row_to_record(row) if row else None

    async def get_latest_by_event_and_user(
        self,
        event_id: str,
        user_id: str,
    ) -> UserFeedbackRecord | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT * FROM user_feedback
                WHERE event_id = ? AND user_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (event_id, user_id),
            ).fetchone()
        return self._row_to_record(row) if row else None

    async def list_by_user(self, user_id: str, limit: int = 100) -> list[UserFeedbackRecord]:
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT * FROM user_feedback
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    @staticmethod
    def _row_to_record(row) -> UserFeedbackRecord:
        return UserFeedbackRecord.model_validate(
            {
                "feedback_id": row["feedback_id"],
                "user_id": row["user_id"],
                "event_id": row["event_id"],
                "decision_id": row["decision_id"],
                "delivery_log_id": row["delivery_log_id"],
                "feedback_type": row["feedback_type"],
                "rating": row["rating"],
                "comment": row["comment"],
                "metadata": json.loads(row["metadata_json"]),
                "created_at": row["created_at"],
            }
        )
