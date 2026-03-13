from __future__ import annotations

import json
from pathlib import Path

from backend.app.core.database import get_connection
from backend.app.services.delivery.models import DigestJob


class DigestJobRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    async def save(self, job: DigestJob) -> None:
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO delivery_digest_jobs (
                    job_id,
                    user_id,
                    window_key,
                    status,
                    task_refs_json,
                    scheduled_at,
                    sent_at,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id, window_key) DO UPDATE SET
                    job_id = excluded.job_id,
                    status = excluded.status,
                    task_refs_json = excluded.task_refs_json,
                    scheduled_at = excluded.scheduled_at,
                    sent_at = excluded.sent_at
                """,
                (
                    job.job_id,
                    job.user_id,
                    job.window_key,
                    job.status,
                    json.dumps(job.task_refs, ensure_ascii=False),
                    job.scheduled_at,
                    job.sent_at,
                    job.created_at,
                ),
            )
            connection.commit()

    async def get_by_user_and_window(self, user_id: str, window_key: str) -> DigestJob | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM delivery_digest_jobs
                WHERE user_id = ? AND window_key = ?
                LIMIT 1
                """,
                (user_id, window_key),
            ).fetchone()
        return self._row_to_job(row) if row else None

    async def list_pending(self, scheduled_before: str | None = None) -> list[DigestJob]:
        query = "SELECT * FROM delivery_digest_jobs WHERE status = 'pending'"
        parameters: list[str] = []
        if scheduled_before is not None:
            query += " AND scheduled_at <= ?"
            parameters.append(scheduled_before)
        query += " ORDER BY scheduled_at ASC"

        with get_connection(self.database_path) as connection:
            rows = connection.execute(query, tuple(parameters)).fetchall()
        return [self._row_to_job(row) for row in rows]

    def _row_to_job(self, row) -> DigestJob:
        return DigestJob(
            job_id=row["job_id"],
            user_id=row["user_id"],
            window_key=row["window_key"],
            status=row["status"],
            task_refs=json.loads(row["task_refs_json"]),
            scheduled_at=row["scheduled_at"],
            sent_at=row["sent_at"],
            created_at=row["created_at"],
        )
