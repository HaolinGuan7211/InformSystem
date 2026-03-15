from __future__ import annotations

from datetime import datetime, timezone

from backend.app.services.campus_auth.szu.ehall_client import SzuEhallClient
from backend.app.services.profile_sampling.models import (
    ProfileSyncRequest,
    RawProfileFragment,
    SchoolSessionHandle,
)
from backend.app.services.profile_sampling.samplers.base import ProfileSampler


class SzuAcademicCompletionSampler(ProfileSampler):
    source_system = "szu_ehall_academic_completion"
    fixture_key = "szu_academic_completion"

    def __init__(self, ehall_client: SzuEhallClient | None = None) -> None:
        self._ehall_client = ehall_client or SzuEhallClient()

    def supports(
        self,
        session_handle: SchoolSessionHandle,
        request: ProfileSyncRequest,
    ) -> bool:
        if request.auth_mode == "offline_fixture":
            return self.fixture_key in request.hints

        target_system = session_handle.metadata.get("target_system")
        return target_system == "ehall" and session_handle.session is not None

    async def sample(
        self,
        session_handle: SchoolSessionHandle,
        request: ProfileSyncRequest,
    ) -> list[RawProfileFragment]:
        if request.auth_mode == "offline_fixture":
            bundle = request.hints.get(self.fixture_key)
            if not isinstance(bundle, dict):
                return []
        else:
            bundle = self._ehall_client.collect_academic_completion(
                self._to_campus_handle(session_handle),
                bynjdm=self._resolve_bynjdm(request),
                page_size=self._resolve_page_size(request),
            )

        collected_at = datetime.now(timezone.utc).isoformat()
        context = bundle.get("context")
        overview = bundle.get("overview")
        student_info = bundle.get("student_info")
        plan_snapshots = bundle.get("plan_snapshots")
        root_nodes = bundle.get("root_nodes")
        child_nodes = bundle.get("child_nodes")
        child_nodes_by_parent = bundle.get("child_nodes_by_parent")
        course_groups = bundle.get("course_groups")
        course_rows = bundle.get("course_rows")
        summary = bundle.get("summary")
        root_summaries = bundle.get("root_summaries")
        by_njdm = bundle.get("by_njdm", self._resolve_bynjdm(request))

        return [
            RawProfileFragment(
                fragment_type="academic_completion_overview",
                source_system=self.source_system,
                payload={
                    "by_njdm": by_njdm,
                    "context": context if isinstance(context, dict) else {},
                    "overview": overview if isinstance(overview, dict) else {},
                    "student_info": student_info if isinstance(student_info, dict) else {},
                    "plan_snapshots": plan_snapshots if isinstance(plan_snapshots, list) else [],
                },
                collected_at=collected_at,
            ),
            RawProfileFragment(
                fragment_type="academic_completion_nodes",
                source_system=self.source_system,
                payload={
                    "by_njdm": by_njdm,
                    "plan_id": (context or {}).get("plan_id") if isinstance(context, dict) else None,
                    "root_nodes": root_nodes if isinstance(root_nodes, list) else [],
                    "child_nodes": child_nodes if isinstance(child_nodes, list) else [],
                    "child_nodes_by_parent": (
                        child_nodes_by_parent if isinstance(child_nodes_by_parent, dict) else {}
                    ),
                    "root_summaries": root_summaries if isinstance(root_summaries, list) else [],
                },
                collected_at=collected_at,
            ),
            RawProfileFragment(
                fragment_type="academic_completion_courses",
                source_system=self.source_system,
                payload={
                    "by_njdm": by_njdm,
                    "plan_id": (context or {}).get("plan_id") if isinstance(context, dict) else None,
                    "course_groups": course_groups if isinstance(course_groups, list) else [],
                    "course_rows": course_rows if isinstance(course_rows, list) else [],
                    "summary": summary if isinstance(summary, dict) else {},
                },
                collected_at=collected_at,
            ),
        ]

    def _resolve_bynjdm(self, request: ProfileSyncRequest) -> str:
        value = request.hints.get("academic_completion_bynjdm")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return SzuEhallClient.DEFAULT_BYNJDM

    def _resolve_page_size(self, request: ProfileSyncRequest) -> int:
        value = request.hints.get("academic_completion_page_size")
        if isinstance(value, int) and value > 0:
            return value
        return SzuEhallClient.DEFAULT_PAGE_SIZE

    def _to_campus_handle(self, session_handle: SchoolSessionHandle):
        from backend.app.services.campus_auth.models import CampusSessionHandle

        return CampusSessionHandle(
            school_code=session_handle.school_code,
            auth_mode=session_handle.auth_mode,
            target_system=str(session_handle.metadata.get("target_system") or ""),
            session=session_handle.session,
            entry_url=session_handle.entry_url,
            authenticated_url=session_handle.authenticated_url,
            metadata=dict(session_handle.metadata),
        )
