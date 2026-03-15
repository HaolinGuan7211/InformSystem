from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.container import build_container
from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.services.ai_processing.model_gateway import MockModelGateway
from backend.app.services.ingestion.connectors.szu_board import SzuBoardParser
from backend.app.services.user_profile.models import NotificationPreference, UserProfile

PROJECT_ROOT = Path(__file__).resolve().parents[4]
FLOW_ROOT = (
    PROJECT_ROOT
    / "mocks"
    / "shared"
    / "golden_flows"
    / "flow_001_graduation_material_submission"
)


@pytest.fixture
def workflow_settings(tmp_path: Path) -> Settings:
    return Settings(
        project_root=PROJECT_ROOT,
        data_dir=tmp_path / "data",
        database_path=tmp_path / "data" / "workflow.db",
        source_config_path=PROJECT_ROOT / "mocks" / "ingestion" / "source_configs.json",
        rule_config_path=PROJECT_ROOT / "mocks" / "rule_engine" / "upstream_inputs" / "rule_configs.json",
        push_policy_path=PROJECT_ROOT / "mocks" / "config" / "downstream_outputs" / "push_policies.json",
    )


@pytest.fixture
def container(workflow_settings: Settings):
    return build_container(workflow_settings)


@pytest.fixture
def client(workflow_settings: Settings) -> TestClient:
    return TestClient(create_app(workflow_settings))


@pytest.fixture
def load_json():
    def _load(path: Path):
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    return _load


@pytest.fixture
def load_text():
    def _load(path: Path) -> str:
        return path.read_text(encoding="utf-8")

    return _load


async def _seed_profile(target_container, load_json) -> UserProfile:
    profile = UserProfile.model_validate(load_json(FLOW_ROOT / "02_user_profile.json"))
    await target_container.user_profile_service.upsert_profile(profile)
    return profile


async def _seed_event(target_container, load_json):
    payload = load_json(PROJECT_ROOT / "mocks" / "ingestion" / "raw_inputs" / "wecom_message.json")
    events = await target_container.webhook_receiver.receive("wecom_cs_notice_group", payload)
    return events[0]


@pytest.mark.asyncio
async def test_workflow_orchestrator_runs_full_chain(container, load_json) -> None:
    profile = await _seed_profile(container, load_json)
    event = await _seed_event(container, load_json)

    result = await container.workflow_orchestrator.run_event(
        event,
        context={"current_time": "2026-03-13T14:00:00+08:00"},
    )

    assert result.total_candidate_users == 1
    assert result.processed_user_count == 1
    assert result.errors == []

    user_run = result.results[0]
    assert user_run.user_profile.user_id == profile.user_id
    assert user_run.rule_result.relevance_status == "relevant"
    assert user_run.rule_result.required_profile_facets == ["identity_core", "graduation_progress"]
    assert user_run.ai_result is not None
    assert user_run.decision_result.decision_action in {"push_now", "push_high"}
    assert [log.status for log in user_run.delivery_logs] == ["sent"]
    history = await container.delivery_log_repository.list_by_task(user_run.delivery_logs[0].task_id)
    assert [log.log_id for log in history] == [user_run.delivery_logs[0].log_id]

    feedback_record = await container.feedback_service.record_user_feedback(
        {
            "feedback_id": "fb_full_chain_useful",
            "user_id": profile.user_id,
            "event_id": event.event_id,
            "decision_id": user_run.decision_result.decision_id,
            "delivery_log_id": user_run.delivery_logs[0].log_id,
            "feedback_type": "useful",
            "rating": 5,
            "comment": "important notice",
            "metadata": {"request_id": "full_chain_useful_feedback"},
            "created_at": "2026-03-13T14:10:00+08:00",
        }
    )
    samples = await container.feedback_service.export_optimization_samples(limit=10)

    assert feedback_record.event_id == event.event_id
    assert any(sample.event_id == event.event_id and sample.user_id == profile.user_id for sample in samples)


@pytest.mark.asyncio
async def test_workflow_orchestrator_continues_when_ai_runtime_disabled(
    workflow_settings: Settings,
    load_json,
    monkeypatch,
) -> None:
    workflow_settings.ai_enabled = False
    disabled_container = build_container(workflow_settings)
    profile = await _seed_profile(disabled_container, load_json)
    event = await _seed_event(disabled_container, load_json)

    async def _unexpected_build_profile_context(*args, **kwargs):
        raise AssertionError("build_profile_context should not run when AI runtime is disabled")

    monkeypatch.setattr(
        disabled_container.user_profile_service,
        "build_profile_context",
        _unexpected_build_profile_context,
    )

    result = await disabled_container.workflow_orchestrator.run_event(
        event,
        context={"current_time": "2026-03-13T14:00:00+08:00"},
    )

    assert result.total_candidate_users == 1
    assert result.processed_user_count == 1
    assert result.errors == []

    user_run = result.results[0]
    assert user_run.user_profile.user_id == profile.user_id
    assert user_run.rule_result.should_invoke_ai is True
    assert user_run.ai_result is None
    assert user_run.decision_result.decision_action in {"push_now", "push_high"}
    assert [log.status for log in user_run.delivery_logs] == ["sent"]

    call_logs = await disabled_container.ai_analysis_repository.list_call_logs(event.event_id, profile.user_id)
    assert [log.status for log in call_logs] == ["skipped"]


@pytest.mark.asyncio
async def test_workflow_orchestrator_skips_profile_context_when_stage1_marks_irrelevant(
    container,
    load_json,
    monkeypatch,
) -> None:
    await _seed_profile(container, load_json)
    event = await _seed_event(container, load_json)
    container.ai_processing_service._model_gateway = MockModelGateway(
        fixture_responses={
            ("stage1", event.event_id, "stu_001"): {
                "output": {
                    "relevance_hint_stage1": "irrelevant",
                    "required_profile_facets": ["identity_core"],
                    "reason_summary_stage1": "轻画像粗筛已明确判定无关。",
                    "confidence": 0.86,
                },
                "raw_request_ref": "wf_stage1_req",
                "raw_response_ref": "wf_stage1_resp",
                "latency_ms": 5,
            }
        }
    )

    async def _unexpected_build_profile_context(*args, **kwargs):
        raise AssertionError("build_profile_context should not run when stage1 is irrelevant")

    monkeypatch.setattr(
        container.user_profile_service,
        "build_profile_context",
        _unexpected_build_profile_context,
    )

    result = await container.workflow_orchestrator.run_event(
        event,
        context={"current_time": "2026-03-13T14:00:00+08:00"},
    )

    user_run = result.results[0]
    assert user_run.ai_result is not None
    assert user_run.ai_result.relevance_hint == "irrelevant"
    assert user_run.ai_result.metadata["analysis_stage"] == "stage1"


@pytest.mark.asyncio
async def test_workflow_orchestrator_builds_profile_context_only_after_stage1_passes(
    container,
    load_json,
    monkeypatch,
) -> None:
    await _seed_profile(container, load_json)
    event = await _seed_event(container, load_json)
    container.ai_processing_service._model_gateway = MockModelGateway(
        fixture_responses={
            ("stage1", event.event_id, "stu_001"): {
                "output": {
                    "relevance_hint_stage1": "candidate",
                    "required_profile_facets": ["identity_core", "graduation_progress"],
                    "reason_summary_stage1": "继续进入重画像精筛。",
                    "confidence": 0.81,
                },
                "raw_request_ref": "wf_stage1_req",
                "raw_response_ref": "wf_stage1_resp",
                "latency_ms": 5,
            },
            (event.event_id, "stu_001"): load_json(
                PROJECT_ROOT
                / "mocks"
                / "ai_processing"
                / "downstream_outputs"
                / "graduation_material_submission__output__mock_gateway_response.json"
            ),
        }
    )

    original_build_profile_context = container.user_profile_service.build_profile_context
    build_profile_context_calls: list[list[str]] = []

    async def _tracking_build_profile_context(*args, **kwargs):
        required_facets = list(kwargs.get("required_facets", []) or [])
        build_profile_context_calls.append(required_facets)
        return await original_build_profile_context(*args, **kwargs)

    monkeypatch.setattr(
        container.user_profile_service,
        "build_profile_context",
        _tracking_build_profile_context,
    )

    result = await container.workflow_orchestrator.run_event(
        event,
        context={"current_time": "2026-03-13T14:00:00+08:00"},
    )

    user_run = result.results[0]
    assert build_profile_context_calls == [["identity_core", "graduation_progress"]]
    assert user_run.ai_result is not None
    assert user_run.ai_result.metadata["analysis_stage"] == "stage2"
    assert user_run.ai_result.metadata["analysis_path"] == "stage1_to_stage2"


def test_replay_api_runs_workflow(client, load_json) -> None:
    container = client.app.state.container
    profile = asyncio.run(_seed_profile(container, load_json))
    event = asyncio.run(_seed_event(container, load_json))

    response = client.post(
        f"/api/v1/ingestion/replay/{event.event_id}",
        json={"context": {"current_time": "2026-03-13T14:00:00+08:00"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["event"]["event_id"] == event.event_id
    assert body["workflow"]["processed_user_count"] == 1
    assert body["workflow"]["results"][0]["user_profile"]["user_id"] == profile.user_id
    assert body["workflow"]["results"][0]["delivery_logs"][0]["status"] == "sent"


@pytest.mark.asyncio
async def test_szu_board_event_runs_through_full_chain(container, load_text) -> None:
    source_config = await container.source_registry.get_source_by_id("szu_campus_board")
    connector = container.connector_manager.get_connector("szu_board_authenticated")
    parser = SzuBoardParser(connector._normalizer)
    detail_html = load_text(PROJECT_ROOT / "mocks" / "ingestion" / "raw_inputs" / "szu_board_detail_student_assistant.html")
    raw_item = parser.parse_detail_page(
        detail_html,
        detail_url="https://www1.szu.edu.cn/board/view.asp?id=569039",
        list_title="马院招聘学生助理",
        raw_identifier="569039",
    )
    event = (await connector.normalize(raw_item, source_config))[0]
    await container.raw_event_repository.save_events([event])

    profile = UserProfile(
        user_id="szu_fixture_student",
        student_id="20260099",
        name="Fixture Student",
        college="马克思主义学院",
        major="思想政治教育",
        grade="2022",
        degree_level="undergraduate",
        identity_tags=["student"],
        graduation_stage=None,
        current_tasks=["校内报名"],
        notification_preference=NotificationPreference(
            channels=["app_push"],
            quiet_hours=["23:00-07:00"],
            digest_enabled=True,
            muted_categories=[],
        ),
        metadata={"fixture": True},
    )
    await container.user_profile_service.upsert_profile(profile)

    result = await container.workflow_orchestrator.run_event(
        event,
        user_ids=[profile.user_id],
        context={"current_time": "2026-03-13T14:00:00+08:00"},
    )

    assert result.processed_user_count == 1
    user_run = result.results[0]
    assert user_run.rule_result.relevance_status == "unknown"
    assert user_run.ai_result is not None
    assert user_run.decision_result.decision_action == "digest"
    assert [log.status for log in user_run.delivery_logs] == ["pending"]
