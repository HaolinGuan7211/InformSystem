from __future__ import annotations

import asyncio
import json
from pathlib import Path

from backend.app.container import build_container
from backend.app.core.config import Settings


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


async def main() -> None:
    settings = Settings()
    container = build_container(settings)
    mock_root = settings.project_root / "mocks" / "ingestion" / "raw_inputs"

    wecom_payload = load_json(mock_root / "wecom_message.json")
    manual_payload = load_json(mock_root / "manual_input.json")

    wecom_events = await container.webhook_receiver.receive("wecom_cs_notice_group", wecom_payload)
    website_count = await container.scheduler.run_source("school_website_notice")
    manual_source = await container.source_registry.get_source_by_id("manual_input_default")
    manual_events = await container.ingestion_service.ingest(manual_payload, manual_source)
    stored_events = await container.raw_event_repository.list_events(limit=10)

    print(f"WeCom accepted: {len(wecom_events)}")
    print(f"Website accepted: {website_count}")
    print(f"Manual accepted: {len(manual_events)}")
    print(f"Stored event ids: {[event.event_id for event in stored_events]}")


if __name__ == "__main__":
    asyncio.run(main())
