from __future__ import annotations

import pytest

from backend.app.services.ingestion.models import SourceEvent


@pytest.mark.asyncio
async def test_raw_event_repository_keeps_first_append_only_record(container) -> None:
    first_event = SourceEvent(
        event_id="evt_append_only",
        source_id="manual_input_default",
        source_type="manual",
        source_name="manual_input",
        channel_type="manual",
        title="第一次写入",
        content_text="第一次内容",
        collected_at="2026-03-15T10:00:00+08:00",
        metadata={"canonical_notice_id": "notice_first"},
    )
    second_event = SourceEvent(
        event_id="evt_append_only",
        source_id="manual_input_default",
        source_type="manual",
        source_name="manual_input",
        channel_type="manual",
        title="第二次写入",
        content_text="第二次内容",
        collected_at="2026-03-15T10:05:00+08:00",
        metadata={"canonical_notice_id": "notice_second"},
    )

    await container.raw_event_repository.save_events([first_event])
    await container.raw_event_repository.save_events([second_event])

    stored = await container.raw_event_repository.get_event_by_id("evt_append_only")

    assert stored is not None
    assert stored.title == "第一次写入"
    assert stored.content_text == "第一次内容"
    assert stored.metadata["canonical_notice_id"] == "notice_first"
