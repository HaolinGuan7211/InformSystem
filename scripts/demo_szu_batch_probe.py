from __future__ import annotations

import argparse
import asyncio
import os
from datetime import datetime
from pathlib import Path

from backend.app.container import build_container
from backend.app.core.config import Settings
from backend.app.services.message_probe import build_default_probe_personas


def build_settings(project_root: Path) -> Settings:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    data_dir = project_root / "backend" / "data" / "demo_szu_batch_probe" / run_id
    settings = Settings(
        project_root=project_root,
        data_dir=data_dir,
        database_path=data_dir / "batch_probe.db",
    )

    # Avoid repeated failed remote AI calls when a provider is selected but no key is loaded.
    if settings.ai_provider == "kimi" and not settings.ai_api_key:
        settings.ai_provider = "mock"
        settings.ai_model_name = "mock-notice-analyzer"
        settings.ai_gateway_endpoint = None

    return settings


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Batch-probe SZU campus board notices.")
    parser.add_argument("--source-id", default="szu_campus_board")
    parser.add_argument("--max-items", type=int, default=4)
    parser.add_argument("--request-delay-seconds", type=float, default=0.8)
    parser.add_argument("--only-useful", action="store_true")
    return parser


async def main() -> None:
    args = build_argument_parser().parse_args()
    if not os.getenv("SZU_BOARD_USERNAME") or not os.getenv("SZU_BOARD_PASSWORD"):
        raise SystemExit("SZU_BOARD_USERNAME and SZU_BOARD_PASSWORD are required")

    project_root = Path(__file__).resolve().parents[1]
    settings = build_settings(project_root)
    container = build_container(settings)

    report = await container.message_probe_service.probe_source(
        args.source_id,
        personas=build_default_probe_personas(),
        max_items=args.max_items,
        parse_overrides={"request_delay_seconds": args.request_delay_seconds},
        context={"current_time": datetime.now().astimezone().isoformat()},
    )

    estimated_requests = 2 + max(report.raw_item_count, args.max_items)
    print(f"Project root: {project_root}")
    print(f"AI provider: {container.settings.ai_provider}")
    print(f"Estimated requests: ~{estimated_requests}")
    print(f"Fetched raw items: {report.raw_item_count}")
    print(f"Accepted events: {report.accepted_event_count}")
    print(f"Dropped events: {report.dropped_event_count}")
    print(f"Useful events: {report.useful_event_count}")
    print(f"Probe personas: {report.persona_count}")

    events = report.events
    if args.only_useful:
        events = [event for event in report.events if event.useful]

    if not events:
        print("No events matched the current filter.")
        return

    for index, event in enumerate(events, start=1):
        print("")
        print(f"[{index}] {event.title or '(untitled)'}")
        print(f"  published_at: {event.published_at}")
        print(f"  useful: {event.useful}")
        print(f"  top_persona: {event.top_persona_label} ({event.top_persona_id})")
        print(f"  top_action: {event.top_decision_action}")
        print(f"  top_priority: {event.top_priority_level}")
        print(f"  usefulness_score: {event.top_usefulness_score}")
        if event.persona_outcomes:
            top = event.persona_outcomes[0]
            print(f"  categories: {top.candidate_categories}")
            print(f"  ai_category: {top.ai_category}")
            print(f"  delivery: {top.delivery_statuses}")
            print(f"  reason: {top.reason_summary}")
        if event.url:
            print(f"  url: {event.url}")
        if event.errors:
            print(f"  errors: {event.errors}")


if __name__ == "__main__":
    asyncio.run(main())
