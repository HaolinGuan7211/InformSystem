from __future__ import annotations

import json
from pathlib import Path

from backend.app.core.database import get_connection
from backend.app.shared.models import OptimizationSample


class SQLiteOptimizationSampleRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    async def save(self, sample: OptimizationSample) -> None:
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO optimization_samples (
                    sample_id,
                    event_id,
                    user_id,
                    rule_analysis_id,
                    ai_result_id,
                    decision_id,
                    delivery_log_id,
                    outcome_label,
                    source,
                    metadata_json,
                    generated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    sample.sample_id,
                    sample.event_id,
                    sample.user_id,
                    sample.rule_analysis_id,
                    sample.ai_result_id,
                    sample.decision_id,
                    sample.delivery_log_id,
                    sample.outcome_label,
                    sample.source,
                    json.dumps(sample.metadata, ensure_ascii=False),
                    sample.generated_at,
                ),
            )
            connection.commit()

    async def list(
        self,
        limit: int = 1000,
        source: str | None = None,
        outcome_label: str | None = None,
    ) -> list[OptimizationSample]:
        query = "SELECT * FROM optimization_samples WHERE 1 = 1"
        params: list[object] = []
        if source is not None:
            query += " AND source = ?"
            params.append(source)
        if outcome_label is not None:
            query += " AND outcome_label = ?"
            params.append(outcome_label)
        query += " ORDER BY generated_at DESC LIMIT ?"
        params.append(limit)

        with get_connection(self.database_path) as connection:
            rows = connection.execute(query, tuple(params)).fetchall()
        return [self._row_to_sample(row) for row in rows]

    @staticmethod
    def _row_to_sample(row) -> OptimizationSample:
        return OptimizationSample.model_validate(
            {
                "sample_id": row["sample_id"],
                "event_id": row["event_id"],
                "user_id": row["user_id"],
                "rule_analysis_id": row["rule_analysis_id"],
                "ai_result_id": row["ai_result_id"],
                "decision_id": row["decision_id"],
                "delivery_log_id": row["delivery_log_id"],
                "outcome_label": row["outcome_label"],
                "source": row["source"],
                "metadata": json.loads(row["metadata_json"]),
                "generated_at": row["generated_at"],
            }
        )
