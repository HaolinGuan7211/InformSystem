from __future__ import annotations

import argparse
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.app.container import build_container
from backend.app.core.config import Settings
from backend.app.services.profile_sampling.models import ProfileSyncRequest
from backend.app.services.user_profile.models import UserProfile
from backend.app.services.user_profile.repositories import SQLiteUserProfileRepository

CORE_PROFILE_FIELDS = ("college", "major", "grade")


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch a small SZU board batch into a local experiment database and evaluate relevance for one user."
    )
    parser.add_argument("--source-id", default="szu_campus_board")
    parser.add_argument("--max-items", type=int, default=10)
    parser.add_argument("--request-delay-seconds", type=float, default=1.2)
    parser.add_argument("--user-id")
    parser.add_argument("--student-id")
    parser.add_argument(
        "--base-database-path",
        default=str(Path("backend") / "data" / "inform_system.db"),
        help="Path to an existing local database used only for reading an already-built user profile.",
    )
    parser.add_argument(
        "--sync-profile",
        action="store_true",
        help="If no suitable local profile exists, or the local profile is missing core identity fields, sync the user profile from SZU ehall into the isolated experiment database.",
    )
    parser.add_argument(
        "--profile-auth-mode",
        default="szu_http_cas_ehall",
        choices=[
            "offline_fixture",
            "browser_cookie_import_ehall",
            "szu_http_cas_ehall",
        ],
    )
    parser.add_argument(
        "--current-time",
        default=None,
        help="Optional ISO timestamp used for workflow evaluation. Defaults to now.",
    )
    return parser


def build_settings(project_root: Path) -> tuple[Settings, Path]:
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    data_dir = project_root / "backend" / "data" / "szu_user_probe" / run_id
    settings = Settings(
        project_root=project_root,
        data_dir=data_dir,
        database_path=data_dir / "probe.db",
    )
    return settings, data_dir


def dump_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def render_markdown_summary(summary: dict[str, Any]) -> str:
    lines = [
        "# SZU Board User Relevance Probe",
        "",
        "## Summary",
        "",
        f"- Run time: `{summary['generated_at']}`",
        f"- Source: `{summary['source_id']}`",
        f"- User: `{summary['profile']['user_id']}` / `{summary['profile'].get('student_id')}` / `{summary['profile'].get('name')}`",
        f"- Profile source: `{summary['profile_source']}`",
        f"- Raw items fetched: `{summary['raw_item_count']}`",
        f"- Accepted events: `{summary['accepted_event_count']}`",
        f"- Related count: `{summary['related_count']}`",
        f"- Unrelated count: `{summary['unrelated_count']}`",
        "",
        "## Results",
        "",
    ]

    for index, item in enumerate(summary["items"], start=1):
        lines.extend(
            [
                f"### {index}. {item['title'] or '(untitled)'}",
                "",
                f"- predicted_relation: `{item['predicted_relation']}`",
                f"- rule_relevance_status: `{item['rule_relevance_status']}`",
                f"- decision_action: `{item['decision_action']}`",
                f"- priority_level: `{item['priority_level']}`",
                f"- published_at: `{item['published_at']}`",
                f"- reason_summary: {item['reason_summary'] or '(none)' }",
                f"- categories: `{item['candidate_categories']}`",
                f"- url: {item['url'] or '(none)'}",
                "",
            ]
        )
    return "\n".join(lines)


async def load_existing_profile(
    database_path: Path,
    *,
    user_id: str | None,
    student_id: str | None,
) -> UserProfile | None:
    if not database_path.exists():
        return None

    repository = SQLiteUserProfileRepository(database_path)
    if user_id:
        return await repository.get_by_user_id(user_id)
    if student_id:
        return await repository.get_by_student_id(student_id)

    refs = await repository.list_profile_refs(limit=1)
    if not refs:
        return None
    return await repository.get_by_user_id(refs[0].user_id)


def collect_missing_core_profile_fields(profile: UserProfile) -> list[str]:
    missing: list[str] = []
    for field_name in CORE_PROFILE_FIELDS:
        value = getattr(profile, field_name)
        if value in (None, ""):
            missing.append(field_name)
    return missing


async def resolve_profile(
    *,
    container,
    project_root: Path,
    args,
) -> tuple[UserProfile, str]:
    student_id = args.student_id or os.getenv("SZU_BOARD_USERNAME")
    base_database_path = Path(args.base_database_path)
    if not base_database_path.is_absolute():
        base_database_path = project_root / base_database_path

    existing_profile = await load_existing_profile(
        base_database_path,
        user_id=args.user_id,
        student_id=student_id,
    )
    if existing_profile is not None:
        missing_core_fields = collect_missing_core_profile_fields(existing_profile)
        if not missing_core_fields:
            await container.user_profile_service.upsert_profile(existing_profile)
            return existing_profile, "existing_local_profile"
        if not args.sync_profile:
            await container.user_profile_service.upsert_profile(existing_profile)
            missing_text = ",".join(missing_core_fields)
            return existing_profile, f"existing_local_profile_incomplete:{missing_text}"
        sync_user_id = existing_profile.user_id
        sync_source = f"profile_sync:{args.profile_auth_mode}:refreshed_missing:{','.join(missing_core_fields)}"
    else:
        if not args.sync_profile:
            raise SystemExit(
                "No suitable local profile was found. Re-run with --sync-profile if you want to sync from ehall."
            )
        sync_user_id = args.user_id
        sync_source = f"profile_sync:{args.profile_auth_mode}"

    if not os.getenv("SZU_BOARD_USERNAME") or not os.getenv("SZU_BOARD_PASSWORD"):
        raise SystemExit("SZU_BOARD_USERNAME and SZU_BOARD_PASSWORD are required for --sync-profile")

    sync_request = ProfileSyncRequest(
        school_code="szu",
        auth_mode=args.profile_auth_mode,
        persist=True,
        dry_run=False,
        user_id=sync_user_id,
        username_env="SZU_BOARD_USERNAME",
        password_env="SZU_BOARD_PASSWORD",
    )
    sync_result = await container.profile_sync_orchestrator.run(sync_request)
    return sync_result.profile, sync_source


def build_source_config(source_config: dict[str, Any], *, max_items: int, request_delay_seconds: float) -> dict[str, Any]:
    parse_config = dict(source_config.get("parse_config", {}))
    parse_config["max_items"] = max_items
    parse_config["request_delay_seconds"] = request_delay_seconds
    return {
        **source_config,
        "enabled": True,
        "parse_config": parse_config,
    }


def derive_predicted_relation(rule_relevance_status: str, decision_action: str) -> str:
    if decision_action in {"push_now", "push_high", "digest"}:
        return "related"
    if rule_relevance_status == "irrelevant" or decision_action in {"ignore", "archive"}:
        return "unrelated"
    return "uncertain"


async def main() -> None:
    args = build_argument_parser().parse_args()
    project_root = Path(__file__).resolve().parents[1]
    settings, output_dir = build_settings(project_root)
    container = build_container(settings)

    if not os.getenv("SZU_BOARD_USERNAME") or not os.getenv("SZU_BOARD_PASSWORD"):
        raise SystemExit("SZU_BOARD_USERNAME and SZU_BOARD_PASSWORD are required")

    profile, profile_source = await resolve_profile(
        container=container,
        project_root=project_root,
        args=args,
    )

    source_config = await container.source_registry.get_source_by_id(args.source_id)
    if source_config is None:
        raise SystemExit(f"Unknown source_id: {args.source_id}")

    resolved_config = build_source_config(
        source_config,
        max_items=args.max_items,
        request_delay_seconds=args.request_delay_seconds,
    )

    connector = container.connector_manager.get_connector(resolved_config["connector_type"])
    raw_items = await connector.fetch(resolved_config)
    accepted_events = await container.ingestion_service.ingest_many(raw_items, resolved_config)

    current_time = args.current_time or datetime.now().astimezone().isoformat()
    items: list[dict[str, Any]] = []
    workflow_payloads: list[dict[str, Any]] = []
    for event in accepted_events:
        workflow = await container.workflow_orchestrator.run_event(
            event,
            user_ids=[profile.user_id],
            context={"current_time": current_time},
        )
        workflow_payload = workflow.model_dump()
        workflow_payloads.append(workflow_payload)
        user_result = workflow.results[0] if workflow.results else None

        if user_result is None:
            items.append(
                {
                    "event_id": event.event_id,
                    "title": event.title,
                    "published_at": event.published_at,
                    "url": event.url,
                    "predicted_relation": "uncertain",
                    "rule_relevance_status": None,
                    "relevance_score": None,
                    "decision_action": None,
                    "priority_level": None,
                    "candidate_categories": [],
                    "reason_summary": None,
                    "errors": workflow_payload["errors"],
                }
            )
            continue

        predicted_relation = derive_predicted_relation(
            user_result.rule_result.relevance_status,
            user_result.decision_result.decision_action,
        )
        items.append(
            {
                "event_id": event.event_id,
                "title": event.title,
                "published_at": event.published_at,
                "url": event.url,
                "predicted_relation": predicted_relation,
                "rule_relevance_status": user_result.rule_result.relevance_status,
                "relevance_score": user_result.rule_result.relevance_score,
                "decision_action": user_result.decision_result.decision_action,
                "priority_level": user_result.decision_result.priority_level,
                "candidate_categories": user_result.rule_result.candidate_categories,
                "reason_summary": user_result.decision_result.reason_summary,
                "errors": workflow_payload["errors"],
            }
        )

    summary = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "source_id": resolved_config["source_id"],
        "source_name": resolved_config["source_name"],
        "profile_source": profile_source,
        "profile": {
            "user_id": profile.user_id,
            "student_id": profile.student_id,
            "name": profile.name,
            "college": profile.college,
            "major": profile.major,
            "grade": profile.grade,
            "degree_level": profile.degree_level,
            "graduation_stage": profile.graduation_stage,
        },
        "raw_item_count": len(raw_items),
        "accepted_event_count": len(accepted_events),
        "related_count": sum(1 for item in items if item["predicted_relation"] == "related"),
        "unrelated_count": sum(1 for item in items if item["predicted_relation"] == "unrelated"),
        "items": items,
    }

    dump_json(output_dir / "profile.json", profile.model_dump())
    dump_json(output_dir / "raw_items.json", raw_items)
    dump_json(output_dir / "source_events.json", [event.model_dump() for event in accepted_events])
    dump_json(output_dir / "workflow_results.json", workflow_payloads)
    dump_json(output_dir / "summary_report.json", summary)
    (output_dir / "summary_report.md").write_text(
        render_markdown_summary(summary),
        encoding="utf-8",
    )

    estimated_requests = 2 + len(raw_items)
    print(f"Output directory: {output_dir}")
    print(f"Profile source: {profile_source}")
    print(f"User: {profile.user_id} / {profile.student_id} / {profile.name}")
    print(f"Estimated board requests: ~{estimated_requests}")
    print(f"Raw items fetched: {len(raw_items)}")
    print(f"Accepted events: {len(accepted_events)}")
    print(f"Related: {summary['related_count']}")
    print(f"Unrelated: {summary['unrelated_count']}")
    for index, item in enumerate(items, start=1):
        print("")
        print(f"[{index}] {item['title'] or '(untitled)'}")
        print(f"  predicted_relation: {item['predicted_relation']}")
        print(f"  rule_relevance_status: {item['rule_relevance_status']}")
        print(f"  decision_action: {item['decision_action']}")
        print(f"  priority_level: {item['priority_level']}")
        print(f"  reason_summary: {item['reason_summary']}")
        if item["url"]:
            print(f"  url: {item['url']}")


if __name__ == "__main__":
    asyncio.run(main())
