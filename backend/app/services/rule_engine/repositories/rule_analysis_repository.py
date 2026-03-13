from __future__ import annotations

import json
from pathlib import Path

from backend.app.core.database import get_connection
from backend.app.services.rule_engine.models import RuleAnalysisResult


class RuleAnalysisRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    async def save(self, result: RuleAnalysisResult) -> None:
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO rule_analysis_results (
                    analysis_id,
                    event_id,
                    user_id,
                    rule_version,
                    candidate_categories_json,
                    matched_rules_json,
                    extracted_signals_json,
                    relevance_status,
                    relevance_score,
                    action_required,
                    deadline_at,
                    urgency_level,
                    risk_level,
                    should_invoke_ai,
                    should_continue,
                    explanation_json,
                    metadata_json,
                    generated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._result_to_row(result),
            )
            connection.commit()

    async def get_by_event_and_user(self, event_id: str, user_id: str) -> RuleAnalysisResult | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT * FROM rule_analysis_results
                WHERE event_id = ? AND user_id = ?
                ORDER BY generated_at DESC
                LIMIT 1
                """,
                (event_id, user_id),
            ).fetchone()
        return self._row_to_result(row) if row else None

    def _result_to_row(self, result: RuleAnalysisResult) -> tuple[str | int | float | None, ...]:
        return (
            result.analysis_id,
            result.event_id,
            result.user_id,
            result.rule_version,
            json.dumps(result.candidate_categories, ensure_ascii=False),
            json.dumps([rule.model_dump() for rule in result.matched_rules], ensure_ascii=False),
            json.dumps(result.extracted_signals, ensure_ascii=False),
            result.relevance_status,
            result.relevance_score,
            self._bool_to_int(result.action_required),
            result.deadline_at,
            result.urgency_level,
            result.risk_level,
            int(result.should_invoke_ai),
            int(result.should_continue),
            json.dumps(result.explanation, ensure_ascii=False),
            json.dumps(result.metadata, ensure_ascii=False),
            result.generated_at,
        )

    def _row_to_result(self, row) -> RuleAnalysisResult:
        payload = {
            "analysis_id": row["analysis_id"],
            "event_id": row["event_id"],
            "user_id": row["user_id"],
            "rule_version": row["rule_version"],
            "candidate_categories": json.loads(row["candidate_categories_json"]),
            "matched_rules": json.loads(row["matched_rules_json"]),
            "extracted_signals": json.loads(row["extracted_signals_json"]),
            "relevance_status": row["relevance_status"],
            "relevance_score": row["relevance_score"],
            "action_required": self._int_to_bool(row["action_required"]),
            "deadline_at": row["deadline_at"],
            "urgency_level": row["urgency_level"],
            "risk_level": row["risk_level"],
            "should_invoke_ai": bool(row["should_invoke_ai"]),
            "should_continue": bool(row["should_continue"]),
            "explanation": json.loads(row["explanation_json"]),
            "metadata": json.loads(row["metadata_json"]),
            "generated_at": row["generated_at"],
        }
        return RuleAnalysisResult.model_validate(payload)

    def _bool_to_int(self, value: bool | None) -> int | None:
        if value is None:
            return None
        return int(value)

    def _int_to_bool(self, value: int | None) -> bool | None:
        if value is None:
            return None
        return bool(value)
