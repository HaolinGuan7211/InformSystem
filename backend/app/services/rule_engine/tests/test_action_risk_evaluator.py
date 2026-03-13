from __future__ import annotations

import pytest

from backend.app.services.ingestion.models import SourceEvent
from backend.app.services.rule_engine.service import RuleEngineService


@pytest.mark.asyncio
async def test_action_risk_evaluator_marks_deadline_submission_as_high_priority(
    rule_engine_service: RuleEngineService,
    source_event: SourceEvent,
    user_profile,
) -> None:
    result = await rule_engine_service.analyze(source_event, user_profile)

    assert result.action_required is True
    assert result.deadline_at == "2026-03-15T23:59:59+08:00"
    assert result.urgency_level == "high"
    assert result.risk_level == "high"
    assert result.should_invoke_ai is True
