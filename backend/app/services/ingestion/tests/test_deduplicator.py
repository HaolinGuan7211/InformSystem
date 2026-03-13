from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_deduplicator_filters_duplicate_content(container, load_mock) -> None:
    source_config = await container.source_registry.get_source_by_id("manual_input_default")
    payload = load_mock("manual_input.json")

    first_batch = await container.ingestion_service.ingest(payload, source_config)
    second_batch = await container.ingestion_service.ingest(payload, source_config)
    stored_events = await container.raw_event_repository.list_events()

    assert len(first_batch) == 1
    assert len(second_batch) == 0
    assert len(stored_events) == 1
    assert stored_events[0].metadata["canonical_notice_id"].startswith("notice_")


@pytest.mark.asyncio
async def test_deduplicator_uses_source_unique_key(container, load_mock) -> None:
    source_config = await container.source_registry.get_source_by_id("wecom_cs_notice_group")
    payload = load_mock("wecom_message.json")

    first_batch = await container.ingestion_service.ingest(payload, source_config)
    second_batch = await container.ingestion_service.ingest(payload, source_config)

    assert len(first_batch) == 1
    assert len(second_batch) == 0

