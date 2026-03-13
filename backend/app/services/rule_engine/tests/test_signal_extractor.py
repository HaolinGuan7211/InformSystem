from __future__ import annotations

import pytest

from backend.app.services.rule_engine.config_loader import RuleConfigLoader
from backend.app.services.rule_engine.preprocessor import EventPreprocessor
from backend.app.services.rule_engine.signal_extractor import SignalExtractor


@pytest.mark.asyncio
async def test_signal_extractor_detects_action_keywords_and_deadline(test_settings, source_event) -> None:
    loader = RuleConfigLoader(test_settings.rule_config_path)
    rules = await loader.load_rules("rule_engine")
    preprocessor = EventPreprocessor()
    extractor = SignalExtractor()

    rule_view = await preprocessor.build_rule_view(source_event)
    signals = await extractor.extract(rule_view, rules)

    assert signals["deadline_text"] == "3月15日前"
    assert signals["deadline_at"] == "2026-03-15T23:59:59+08:00"
    assert "提交" in signals["action_keywords"]
    assert "审核材料" in signals["action_keywords"]
