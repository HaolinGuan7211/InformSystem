from __future__ import annotations

import json
from pathlib import Path

from backend.app.core.database import get_connection
from backend.app.services.ai_processing.models import AICallLog, AIAnalysisResult, AIExtractedField


class SQLiteAIAnalysisRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path

    async def save(self, result: AIAnalysisResult) -> None:
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO ai_analysis_results (
                    ai_result_id,
                    event_id,
                    user_id,
                    model_name,
                    prompt_version,
                    summary,
                    normalized_category,
                    action_items_json,
                    extracted_fields_json,
                    relevance_hint,
                    urgency_hint,
                    risk_hint,
                    confidence,
                    needs_human_review,
                    raw_response_ref,
                    metadata_json,
                    generated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                self._result_to_row(result),
            )
            connection.commit()

    async def get_by_event_and_user(
        self,
        event_id: str,
        user_id: str,
        model_name: str | None = None,
        prompt_version: str | None = None,
    ) -> AIAnalysisResult | None:
        query = "SELECT * FROM ai_analysis_results WHERE event_id = ? AND user_id = ?"
        parameters: list[str] = [event_id, user_id]
        if model_name is not None:
            query += " AND model_name = ?"
            parameters.append(model_name)
        if prompt_version is not None:
            query += " AND prompt_version = ?"
            parameters.append(prompt_version)
        query += " ORDER BY generated_at DESC LIMIT 1"

        with get_connection(self.database_path) as connection:
            row = connection.execute(query, tuple(parameters)).fetchone()
        return self._row_to_result(row) if row else None

    async def save_call_log(self, call_log: AICallLog) -> None:
        with get_connection(self.database_path) as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO ai_call_logs (
                    call_id,
                    event_id,
                    user_id,
                    model_name,
                    prompt_version,
                    status,
                    latency_ms,
                    error_message,
                    raw_request_ref,
                    raw_response_ref,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    call_log.call_id,
                    call_log.event_id,
                    call_log.user_id,
                    call_log.model_name,
                    call_log.prompt_version,
                    call_log.status,
                    call_log.latency_ms,
                    call_log.error_message,
                    call_log.raw_request_ref,
                    call_log.raw_response_ref,
                    call_log.created_at,
                ),
            )
            connection.commit()

    async def list_call_logs(self, event_id: str, user_id: str) -> list[AICallLog]:
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT * FROM ai_call_logs
                WHERE event_id = ? AND user_id = ?
                ORDER BY created_at ASC
                """,
                (event_id, user_id),
            ).fetchall()
        return [self._row_to_call_log(row) for row in rows]

    @staticmethod
    def _result_to_row(result: AIAnalysisResult) -> tuple[object, ...]:
        return (
            result.ai_result_id,
            result.event_id,
            result.user_id,
            result.model_name,
            result.prompt_version,
            result.summary,
            result.normalized_category,
            json.dumps(result.action_items, ensure_ascii=False),
            json.dumps([field.model_dump() for field in result.extracted_fields], ensure_ascii=False),
            result.relevance_hint,
            result.urgency_hint,
            result.risk_hint,
            result.confidence,
            int(result.needs_human_review),
            result.raw_response_ref,
            json.dumps(result.metadata, ensure_ascii=False),
            result.generated_at,
        )

    @staticmethod
    def _row_to_result(row) -> AIAnalysisResult:
        return AIAnalysisResult(
            ai_result_id=row["ai_result_id"],
            event_id=row["event_id"],
            user_id=row["user_id"],
            model_name=row["model_name"],
            prompt_version=row["prompt_version"],
            summary=row["summary"],
            normalized_category=row["normalized_category"],
            action_items=json.loads(row["action_items_json"]),
            extracted_fields=[
                AIExtractedField.model_validate(item)
                for item in json.loads(row["extracted_fields_json"])
            ],
            relevance_hint=row["relevance_hint"],
            urgency_hint=row["urgency_hint"],
            risk_hint=row["risk_hint"],
            confidence=row["confidence"],
            needs_human_review=bool(row["needs_human_review"]),
            raw_response_ref=row["raw_response_ref"],
            metadata=json.loads(row["metadata_json"]),
            generated_at=row["generated_at"],
        )

    @staticmethod
    def _row_to_call_log(row) -> AICallLog:
        return AICallLog(
            call_id=row["call_id"],
            event_id=row["event_id"],
            user_id=row["user_id"],
            model_name=row["model_name"],
            prompt_version=row["prompt_version"],
            status=row["status"],
            latency_ms=row["latency_ms"],
            error_message=row["error_message"],
            raw_request_ref=row["raw_request_ref"],
            raw_response_ref=row["raw_response_ref"],
            created_at=row["created_at"],
        )
