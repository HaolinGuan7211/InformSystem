from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from backend.app.services.ingestion.connector_manager import ConnectorManager
from backend.app.services.ingestion.registry import SourceRegistry
from backend.app.services.ingestion.service import IngestionService
from backend.app.services.message_probe.models import BatchProbeReport, ProbeEventReport, ProbePersona, ProbePersonaOutcome
from backend.app.services.user_profile.models import NotificationPreference, UserProfile
from backend.app.services.user_profile.service import UserProfileService
from backend.app.workflows.models import WorkflowRunResult, WorkflowUserRun
from backend.app.workflows.orchestrator import WorkflowOrchestrator


class MessageProbeService:
    _ACTION_WEIGHT = {
        "push_now": 0.40,
        "push_high": 0.34,
        "digest": 0.18,
        "archive": 0.05,
        "ignore": 0.0,
    }
    _RELEVANCE_WEIGHT = {
        "relevant": 0.18,
        "unknown": 0.08,
        "irrelevant": 0.0,
    }

    def __init__(
        self,
        source_registry: SourceRegistry,
        connector_manager: ConnectorManager,
        ingestion_service: IngestionService,
        workflow_orchestrator: WorkflowOrchestrator,
        user_profile_service: UserProfileService,
        timezone_offset: str = "+08:00",
    ) -> None:
        self._source_registry = source_registry
        self._connector_manager = connector_manager
        self._ingestion_service = ingestion_service
        self._workflow_orchestrator = workflow_orchestrator
        self._user_profile_service = user_profile_service
        self._timezone = self._parse_timezone(timezone_offset)

    async def probe_source(
        self,
        source_id: str,
        personas: list[ProbePersona] | None = None,
        *,
        max_items: int | None = None,
        parse_overrides: dict[str, Any] | None = None,
        source_overrides: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> BatchProbeReport:
        source_config = await self._source_registry.get_source_by_id(source_id)
        if source_config is None:
            raise ValueError(f"Unknown source_id: {source_id}")

        resolved_config = self._merge_source_config(
            source_config,
            max_items=max_items,
            parse_overrides=parse_overrides,
            source_overrides=source_overrides,
        )
        resolved_personas = self._normalize_personas(personas or build_default_probe_personas())
        await self._upsert_personas(resolved_personas)

        connector = self._connector_manager.get_connector(resolved_config["connector_type"])
        raw_items = await connector.fetch(resolved_config)
        accepted_events = await self._ingestion_service.ingest_many(raw_items, resolved_config)

        persona_lookup = {persona.profile.user_id: persona for persona in resolved_personas}
        workflow_context = dict(context or {})
        persona_user_ids = list(persona_lookup)
        event_reports: list[ProbeEventReport] = []
        for event in accepted_events:
            workflow = await self._workflow_orchestrator.run_event(
                event,
                user_ids=persona_user_ids,
                context=workflow_context,
            )
            event_reports.append(self._build_event_report(workflow, persona_lookup))

        event_reports.sort(
            key=lambda item: (item.useful, item.top_usefulness_score, item.published_at or ""),
            reverse=True,
        )

        useful_event_count = sum(1 for event in event_reports if event.useful)
        return BatchProbeReport(
            source_id=resolved_config["source_id"],
            source_name=resolved_config["source_name"],
            raw_item_count=len(raw_items),
            accepted_event_count=len(accepted_events),
            dropped_event_count=max(0, len(raw_items) - len(accepted_events)),
            persona_count=len(resolved_personas),
            useful_event_count=useful_event_count,
            generated_at=self._now_iso(),
            events=event_reports,
        )

    def _merge_source_config(
        self,
        source_config: dict[str, Any],
        *,
        max_items: int | None,
        parse_overrides: dict[str, Any] | None,
        source_overrides: dict[str, Any] | None,
    ) -> dict[str, Any]:
        merged = dict(source_config)
        if source_overrides:
            merged.update({key: value for key, value in source_overrides.items() if key != "parse_config"})

        parse_config = dict(source_config.get("parse_config", {}))
        if isinstance(source_overrides, dict) and isinstance(source_overrides.get("parse_config"), dict):
            parse_config.update(source_overrides["parse_config"])
        if parse_overrides:
            parse_config.update(parse_overrides)
        if max_items is not None:
            parse_config["max_items"] = max_items

        merged["enabled"] = True
        merged["parse_config"] = parse_config
        return merged

    def _normalize_personas(self, personas: list[ProbePersona]) -> list[ProbePersona]:
        normalized: list[ProbePersona] = []
        seen_persona_ids: set[str] = set()
        seen_user_ids: set[str] = set()

        for persona in personas:
            if persona.persona_id in seen_persona_ids:
                raise ValueError(f"Duplicate persona_id: {persona.persona_id}")
            if persona.profile.user_id in seen_user_ids:
                raise ValueError(f"Duplicate persona user_id: {persona.profile.user_id}")
            seen_persona_ids.add(persona.persona_id)
            seen_user_ids.add(persona.profile.user_id)
            normalized.append(persona)
        return normalized

    async def _upsert_personas(self, personas: list[ProbePersona]) -> None:
        for persona in personas:
            await self._user_profile_service.upsert_profile(persona.profile)

    def _build_event_report(
        self,
        workflow: WorkflowRunResult,
        persona_lookup: dict[str, ProbePersona],
    ) -> ProbeEventReport:
        outcomes: list[ProbePersonaOutcome] = []
        for result in workflow.results:
            outcomes.append(self._build_persona_outcome(result, persona_lookup))

        outcomes.sort(key=lambda item: item.usefulness_score, reverse=True)
        top = outcomes[0] if outcomes else None
        return ProbeEventReport(
            event_id=workflow.event.event_id,
            title=workflow.event.title,
            published_at=workflow.event.published_at,
            url=workflow.event.url,
            source_name=workflow.event.source_name,
            top_usefulness_score=top.usefulness_score if top else 0.0,
            useful=any(outcome.useful for outcome in outcomes),
            top_persona_id=top.persona_id if top else None,
            top_persona_label=top.label if top else None,
            top_decision_action=top.decision_action if top else None,
            top_priority_level=top.priority_level if top else None,
            top_reason_summary=top.reason_summary if top else None,
            persona_outcomes=outcomes,
            errors=[f"{item.user_id}: {item.error_message}" for item in workflow.errors],
        )

    def _build_persona_outcome(
        self,
        result: WorkflowUserRun,
        persona_lookup: dict[str, ProbePersona],
    ) -> ProbePersonaOutcome:
        persona = persona_lookup[result.user_profile.user_id]
        delivery_statuses = [log.status for log in result.delivery_logs]
        usefulness_score = self._score_user_run(result, delivery_statuses)
        useful = self._is_useful(result)
        return ProbePersonaOutcome(
            persona_id=persona.persona_id,
            label=persona.label,
            user_id=result.user_profile.user_id,
            relevance_status=result.rule_result.relevance_status,
            relevance_score=result.rule_result.relevance_score,
            decision_action=result.decision_result.decision_action,
            priority_level=result.decision_result.priority_level,
            priority_score=result.decision_result.priority_score,
            candidate_categories=result.rule_result.candidate_categories,
            matched_rule_ids=[rule.rule_id for rule in result.rule_result.matched_rules],
            should_invoke_ai=result.rule_result.should_invoke_ai,
            ai_category=result.ai_result.normalized_category if result.ai_result else None,
            ai_summary=result.ai_result.summary if result.ai_result else None,
            delivery_statuses=delivery_statuses,
            reason_summary=result.decision_result.reason_summary,
            usefulness_score=usefulness_score,
            useful=useful,
            metadata={
                "action_required": result.rule_result.action_required,
                "deadline_at": result.rule_result.deadline_at,
            },
        )

    def _is_useful(self, result: WorkflowUserRun) -> bool:
        action = result.decision_result.decision_action
        relevance_status = result.rule_result.relevance_status
        return action in {"push_now", "push_high"} or (action == "digest" and relevance_status != "irrelevant")

    def _score_user_run(
        self,
        result: WorkflowUserRun,
        delivery_statuses: list[str],
    ) -> float:
        priority_component = min(max(result.decision_result.priority_score, 0.0), 100.0) / 100.0 * 0.5
        action_component = self._ACTION_WEIGHT[result.decision_result.decision_action]
        relevance_component = self._RELEVANCE_WEIGHT[result.rule_result.relevance_status]
        delivery_component = 0.04 if "sent" in delivery_statuses else 0.02 if "pending" in delivery_statuses else 0.0
        return round(min(1.0, priority_component + action_component + relevance_component + delivery_component), 4)

    def _now_iso(self) -> str:
        return datetime.now(self._timezone).isoformat()

    @staticmethod
    def _parse_timezone(value: str) -> timezone:
        sign = -1 if value.startswith("-") else 1
        normalized = value[1:] if value[:1] in {"+", "-"} else value
        hours_text, minutes_text = normalized.split(":", maxsplit=1)
        offset = timedelta(hours=int(hours_text), minutes=int(minutes_text))
        return timezone(sign * offset)


def build_default_probe_personas() -> list[ProbePersona]:
    base_preference = NotificationPreference(
        channels=["app_push", "email"],
        quiet_hours=["23:00-07:00"],
        digest_enabled=True,
        muted_categories=[],
    )
    return [
        ProbePersona(
            persona_id="general_undergraduate",
            label="General Undergraduate",
            description="A typical undergraduate student.",
            profile=UserProfile(
                user_id="probe_general_undergraduate",
                student_id="PROBE_U001",
                name="General Undergraduate",
                college="Computer Science",
                major="Software Engineering",
                grade="2023",
                degree_level="undergraduate",
                identity_tags=["student"],
                graduation_stage=None,
                current_tasks=["course_selection"],
                notification_preference=base_preference,
                metadata={"probe_persona": True},
            ),
        ),
        ProbePersona(
            persona_id="graduating_undergraduate",
            label="Graduating Undergraduate",
            description="A senior student preparing graduation review materials.",
            profile=UserProfile(
                user_id="probe_graduating_undergraduate",
                student_id="PROBE_U002",
                name="Graduating Undergraduate",
                college="Computer Science",
                major="Software Engineering",
                grade="2022",
                degree_level="undergraduate",
                identity_tags=["student"],
                graduation_stage="graduation_review",
                current_tasks=["graduation_material_submission"],
                notification_preference=base_preference,
                metadata={"probe_persona": True},
            ),
        ),
        ProbePersona(
            persona_id="campus_job_seeker",
            label="Campus Job Seeker",
            description="A student interested in assistant and campus job postings.",
            profile=UserProfile(
                user_id="probe_campus_job_seeker",
                student_id="PROBE_U003",
                name="Campus Job Seeker",
                college="Economics",
                major="Finance",
                grade="2024",
                degree_level="undergraduate",
                identity_tags=["student", "job_seeker"],
                graduation_stage=None,
                current_tasks=["part_time_job_search"],
                notification_preference=base_preference,
                metadata={"probe_persona": True},
            ),
        ),
        ProbePersona(
            persona_id="graduate_researcher",
            label="Graduate Researcher",
            description="A graduate student interested in research and short-course opportunities.",
            profile=UserProfile(
                user_id="probe_graduate_researcher",
                student_id="PROBE_G001",
                name="Graduate Researcher",
                college="Medicine",
                major="Biomedical Engineering",
                grade="2024",
                degree_level="graduate",
                identity_tags=["student", "research"],
                graduation_stage=None,
                current_tasks=["short_course_registration", "research_project"],
                notification_preference=base_preference,
                metadata={"probe_persona": True},
            ),
        ),
    ]
