from __future__ import annotations

from typing import Any

from backend.app.services.ai_processing.models import AIExtractedField


class FieldExtractor:
    async def extract(self, raw_response: dict[str, Any]) -> list[AIExtractedField]:
        extracted_fields: list[AIExtractedField] = []
        raw_fields = raw_response.get("extracted_fields", [])
        if isinstance(raw_fields, list):
            for item in raw_fields:
                if not isinstance(item, dict):
                    continue
                field_name = item.get("field_name")
                if not isinstance(field_name, str) or not field_name.strip():
                    continue
                extracted_fields.append(
                    AIExtractedField(
                        field_name=field_name.strip(),
                        field_value=item.get("field_value"),
                        confidence=self._coerce_confidence(item.get("confidence")),
                    )
                )

        deadline_at = raw_response.get("deadline_at")
        if deadline_at and not any(field.field_name == "deadline_at" for field in extracted_fields):
            extracted_fields.append(
                AIExtractedField(
                    field_name="deadline_at",
                    field_value=deadline_at,
                    confidence=0.8,
                )
            )
        return extracted_fields

    @staticmethod
    def _coerce_confidence(value: Any) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(parsed, 1.0))
