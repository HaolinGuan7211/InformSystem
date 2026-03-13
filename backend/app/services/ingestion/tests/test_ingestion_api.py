from __future__ import annotations

import pytest


def test_webhook_api_accepts_payload(client, load_mock) -> None:
    response = client.post("/api/v1/webhooks/wecom_cs_notice_group", json=load_mock("wecom_message.json"))

    assert response.status_code == 200
    assert response.json() == {"success": True, "accepted": 1}


def test_replay_api_returns_stored_event(client, load_mock) -> None:
    ingest_response = client.post("/api/v1/ingestion/manual", json=load_mock("manual_input.json"))
    event_id = ingest_response.json()["event_ids"][0]

    replay_response = client.post(f"/api/v1/ingestion/replay/{event_id}")

    assert replay_response.status_code == 200
    body = replay_response.json()
    assert body["success"] is True
    assert body["event"]["event_id"] == event_id
    assert body["event"]["source_id"] == "manual_input_default"


@pytest.mark.asyncio
async def test_scheduler_runs_website_fetch(container) -> None:
    accepted = await container.scheduler.run_source("school_website_notice")
    stored_events = await container.raw_event_repository.list_events()

    assert accepted == 1
    assert len(stored_events) == 1
    assert stored_events[0].source_id == "school_website_notice"
