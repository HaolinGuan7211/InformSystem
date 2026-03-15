from __future__ import annotations

import pytest

from backend.app.services.message_probe.service import build_default_probe_personas


def test_default_probe_personas_are_unique() -> None:
    personas = build_default_probe_personas()

    assert len(personas) == 4
    assert len({persona.persona_id for persona in personas}) == 4
    assert len({persona.profile.user_id for persona in personas}) == 4


@pytest.mark.asyncio
async def test_probe_source_surfaces_useful_notice(container) -> None:
    mock_payload = {
        "url": "https://example.edu.cn/notice/grad-001",
        "title": "关于2026届本科毕业资格审核材料提交的通知",
        "html": "<html><body>请各学院于3月15日前组织毕业生提交相关材料。</body></html>",
        "published_at": "2026-03-12 09:00:00",
        "attachments": [],
        "author": "教务部",
    }

    report = await container.message_probe_service.probe_source(
        "school_website_notice",
        personas=build_default_probe_personas(),
        max_items=1,
        source_overrides={"mock_payloads": [mock_payload]},
        context={"current_time": "2026-03-13T10:21:00+08:00"},
    )

    assert report.raw_item_count == 1
    assert report.accepted_event_count == 1
    assert report.useful_event_count == 1
    assert len(report.events) == 1

    event = report.events[0]
    assert event.useful is True
    assert event.top_persona_id == "graduating_undergraduate"
    assert event.top_decision_action in {"push_now", "push_high", "digest"}
    assert event.persona_outcomes[0].useful is True
    assert event.persona_outcomes[0].candidate_categories
