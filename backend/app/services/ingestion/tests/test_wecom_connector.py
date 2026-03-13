from __future__ import annotations

import pytest

from backend.app.services.ingestion.models import SourceEvent


@pytest.mark.asyncio
async def test_wecom_payload_normalizes_to_source_event(container, load_mock) -> None:
    source_config = await container.source_registry.get_source_by_id("wecom_cs_notice_group")
    connector = container.connector_manager.get_connector("wecom_webhook")

    events = await connector.normalize(load_mock("wecom_message.json"), source_config)

    assert len(events) == 1
    event = events[0]
    assert isinstance(event, SourceEvent)
    assert event.source_id == "wecom_cs_notice_group"
    assert event.source_name == "计算机学院通知群"
    assert event.channel_type == "group_message"
    assert event.author == "辅导员A"
    assert event.content_text == "请2026届毕业生于3月15日前提交毕业资格审核材料"
    assert event.published_at == "2026-03-13T10:20:00+08:00"
    assert event.metadata["raw_msgid"] == "raw_wecom_001"

