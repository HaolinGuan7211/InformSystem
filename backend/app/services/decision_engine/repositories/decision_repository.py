from __future__ import annotations

import json
from pathlib import Path

from backend.app.core.database import get_connection
from backend.app.shared.models import DecisionResult


class SQLiteDecisionRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    async def save(self, result: DecisionResult) -> None:
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO decision_results (
                    decision_id,
                    event_id,
                    user_id,
                    relevance_status,
                    priority_score,
                    priority_level,
                    decision_action,
                    delivery_timing,
                    delivery_channels_json,
                    action_required,
                    deadline_at,
                    reason_summary,
                    explanations_json,
                    evidences_json,
                    policy_version,
                    metadata_json,
                    generated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(event_id, user_id, policy_version) DO UPDATE SET
                    decision_id = excluded.decision_id,
                    relevance_status = excluded.relevance_status,
                    priority_score = excluded.priority_score,
                    priority_level = excluded.priority_level,
                    decision_action = excluded.decision_action,
                    delivery_timing = excluded.delivery_timing,
                    delivery_channels_json = excluded.delivery_channels_json,
                    action_required = excluded.action_required,
                    deadline_at = excluded.deadline_at,
                    reason_summary = excluded.reason_summary,
                    explanations_json = excluded.explanations_json,
                    evidences_json = excluded.evidences_json,
                    metadata_json = excluded.metadata_json,
                    generated_at = excluded.generated_at
                """,
                self._result_to_row(result),
            )
            connection.commit()

    async def get_by_event_and_user(
        self,
        event_id: str,
        user_id: str,
        policy_version: str | None = None,
    ) -> DecisionResult | None:
        query = "SELECT * FROM decision_results WHERE event_id = ? AND user_id = ?"
        params: list[str] = [event_id, user_id]

        if policy_version is not None:
            query += " AND policy_version = ?"
            params.append(policy_version)

        query += " ORDER BY generated_at DESC LIMIT 1"

        with get_connection(self.database_path) as connection:
            row = connection.execute(query, tuple(params)).fetchone()

        return self._row_to_result(row) if row else None

    def _result_to_row(self, result: DecisionResult) -> tuple[object, ...]:
        return (
            result.decision_id,
            result.event_id,
            result.user_id,
            result.relevance_status,
            result.priority_score,
            result.priority_level,
            result.decision_action,
            result.delivery_timing,
            json.dumps(result.delivery_channels, ensure_ascii=False),
            result.action_required,
            result.deadline_at,
            result.reason_summary,
            json.dumps(result.explanations, ensure_ascii=False),
            json.dumps([evidence.model_dump() for evidence in result.evidences], ensure_ascii=False),
            result.policy_version,
            json.dumps(result.metadata, ensure_ascii=False),
            result.generated_at,
        )

    def _row_to_result(self, row) -> DecisionResult:
        return DecisionResult(
            decision_id=row["decision_id"],
            event_id=row["event_id"],
            user_id=row["user_id"],
            relevance_status=row["relevance_status"],
            priority_score=float(row["priority_score"]),
            priority_level=row["priority_level"],
            decision_action=row["decision_action"],
            delivery_timing=row["delivery_timing"],
            delivery_channels=json.loads(row["delivery_channels_json"]),
            action_required=None if row["action_required"] is None else bool(row["action_required"]),
            deadline_at=row["deadline_at"],
            reason_summary=row["reason_summary"],
            explanations=json.loads(row["explanations_json"]),
            evidences=json.loads(row["evidences_json"]),
            policy_version=row["policy_version"],
            metadata=json.loads(row["metadata_json"]),
            generated_at=row["generated_at"],
        )
