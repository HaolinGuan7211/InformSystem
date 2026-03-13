from __future__ import annotations

import pytest

from backend.app.services.ingestion.models import SourceEvent
from backend.app.services.rule_engine.service import RuleEngineService
from backend.app.services.user_profile.models import UserProfile


@pytest.mark.asyncio
async def test_graduate_identity_matches_graduation_notice(rule_engine_service: RuleEngineService, source_event, user_profile: UserProfile) -> None:
    result = await rule_engine_service.analyze(source_event, user_profile)

    assert result.relevance_status == "relevant"
    assert result.relevance_score == 0.92
    assert "graduation" in result.candidate_categories


@pytest.mark.asyncio
async def test_non_graduate_profile_is_marked_irrelevant_for_graduate_notice(
    rule_engine_service: RuleEngineService,
    source_event: SourceEvent,
    user_profile: UserProfile,
) -> None:
    non_graduate = user_profile.model_copy(update={"identity_tags": [], "graduation_stage": None})

    result = await rule_engine_service.analyze(source_event, non_graduate)

    assert result.relevance_status == "irrelevant"
    assert result.relevance_score <= 0.2
    assert result.should_continue is True
