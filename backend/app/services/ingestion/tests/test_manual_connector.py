from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_manual_input_normalizes_to_source_event(container, load_mock) -> None:
    source_config = await container.source_registry.get_source_by_id("manual_input_default")
    connector = container.connector_manager.get_connector("manual_input")

    events = await connector.normalize(load_mock("manual_input.json"), source_config)

    assert len(events) == 1
    event = events[0]
    assert event.source_id == "manual_input_default"
    assert event.source_name == "manual_input"
    assert event.channel_type == "manual"
    assert event.title == "学分讲座通知"
    assert event.content_text.startswith("本周五晚讲座可认定美育学分")
    assert event.published_at == "2026-03-13T12:00:00+08:00"

