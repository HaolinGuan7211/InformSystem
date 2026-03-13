from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_website_payload_normalizes_to_source_event(container, load_mock) -> None:
    source_config = await container.source_registry.get_source_by_id("school_website_notice")
    connector = container.connector_manager.get_connector("website_html")

    events = await connector.normalize(load_mock("website_notice.json"), source_config)

    assert len(events) == 1
    event = events[0]
    assert event.title == "关于2026届本科毕业资格审核材料提交的通知"
    assert "3月15日前组织毕业生提交相关材料" in event.content_text
    assert event.url == "https://xxx.edu.cn/notice/123"
    assert len(event.attachments) == 1
    assert event.attachments[0].name == "毕业审核表.docx"
    assert event.published_at == "2026-03-12T09:00:00+08:00"


@pytest.mark.asyncio
async def test_website_connector_handles_empty_optional_fields(container) -> None:
    source_config = await container.source_registry.get_source_by_id("school_website_notice")
    connector = container.connector_manager.get_connector("website_html")

    payload = {
        "url": "https://xxx.edu.cn/notice/empty",
        "html": "<html><body>只有正文</body></html>",
        "published_at": "2026-03-12 09:00:00",
    }
    events = await connector.normalize(payload, source_config)

    assert events[0].title is None
    assert events[0].author is None
    assert events[0].attachments == []


@pytest.mark.asyncio
async def test_invalid_time_format_raises_error(container, load_mock) -> None:
    source_config = await container.source_registry.get_source_by_id("school_website_notice")
    connector = container.connector_manager.get_connector("website_html")
    payload = load_mock("website_notice.json")
    payload["published_at"] = "2026/99/99"

    with pytest.raises(ValueError, match="Unsupported datetime format"):
        await connector.normalize(payload, source_config)

