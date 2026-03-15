from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from backend.app.services.profile_compat.mappers.base import ProfileMapper
from backend.app.services.profile_compat.merge import ProfileMergePolicy
from backend.app.services.profile_compat.models import NormalizedProfileDraft
from backend.app.services.profile_sampling.models import ProfileSamplingResult, ProfileSyncRequest, RawProfileFragment
from backend.app.services.user_profile.models import CourseInfo, UserProfile

STUDENT_ID_GRADE_RE = re.compile(r"^(20\d{2})\d{4,}$")
YEAR_TOKEN_RE = re.compile(r"(20\d{2})")


class SzuProfileMapper(ProfileMapper):
    def __init__(self, merge_policy: ProfileMergePolicy | None = None) -> None:
        self._merge_policy = merge_policy or ProfileMergePolicy()

    def map(
        self,
        *,
        request: ProfileSyncRequest,
        sampling_result: ProfileSamplingResult,
        existing_profile: UserProfile | None = None,
    ) -> NormalizedProfileDraft:
        proposed_values: dict[str, Any] = {}
        field_sources: dict[str, str] = {}
        warnings = list(sampling_result.warnings)

        legacy_credit_fragments: list[RawProfileFragment] = []
        academic_completion_fragments: dict[str, RawProfileFragment] = {}

        for fragment in sampling_result.fragments:
            if fragment.fragment_type == "identity":
                self._merge_identity_fragment(fragment.payload, fragment.source_system, proposed_values, field_sources)
            elif fragment.fragment_type == "courses":
                self._merge_courses_fragment(fragment.payload, fragment.source_system, proposed_values, field_sources)
            elif fragment.fragment_type == "credit_status":
                legacy_credit_fragments.append(fragment)
            elif fragment.fragment_type.startswith("academic_completion_"):
                academic_completion_fragments[fragment.fragment_type] = fragment

        for fragment in legacy_credit_fragments:
            self._merge_credit_status_fragment(fragment, request.school_code, proposed_values, field_sources)

        if academic_completion_fragments:
            self._merge_academic_completion_fragments(
                request=request,
                fragments=academic_completion_fragments,
                proposed_values=proposed_values,
                field_sources=field_sources,
            )

        self._merge_hints(request.hints, request.school_code, proposed_values, field_sources)
        self._apply_derivations(proposed_values, field_sources)

        proposed_values["metadata"] = self._build_metadata(
            request=request,
            sampling_result=sampling_result,
            existing_profile=existing_profile,
            field_sources=field_sources,
        )

        profile = self._merge_policy.merge(
            school_code=request.school_code,
            proposed_values=proposed_values,
            existing_profile=existing_profile,
            preferred_user_id=request.user_id,
        )
        missing_fields = self._collect_missing_fields(profile)

        return NormalizedProfileDraft(
            school_code=request.school_code,
            profile=profile,
            missing_fields=missing_fields,
            warnings=warnings,
            failed_sources=list(sampling_result.failed_sources),
            field_sources=field_sources,
            metadata=proposed_values["metadata"],
        )

    def _merge_identity_fragment(
        self,
        payload: dict[str, Any],
        source_system: str,
        proposed_values: dict[str, Any],
        field_sources: dict[str, str],
    ) -> None:
        for field_name in ["student_id", "name", "college", "major", "grade", "degree_level"]:
            value = payload.get(field_name)
            normalized_value = self._normalize_identity_field(field_name, value)
            if normalized_value in (None, ""):
                continue
            proposed_values[field_name] = normalized_value
            field_sources[field_name] = source_system

        if isinstance(payload.get("identity_tags"), list):
            tags = [str(tag).strip() for tag in payload["identity_tags"] if str(tag).strip()]
            if tags:
                proposed_values["identity_tags"] = tags
                field_sources["identity_tags"] = source_system

        metadata_payload = payload.get("metadata")
        if isinstance(metadata_payload, dict) and metadata_payload:
            metadata = proposed_values.setdefault("metadata", {})
            metadata.update(metadata_payload)

    def _merge_courses_fragment(
        self,
        payload: dict[str, Any],
        source_system: str,
        proposed_values: dict[str, Any],
        field_sources: dict[str, str],
    ) -> None:
        raw_courses = payload.get("courses")
        if not isinstance(raw_courses, list):
            return

        courses: list[CourseInfo] = []
        for item in raw_courses:
            if not isinstance(item, dict):
                continue
            course_id = item.get("course_id")
            course_name = item.get("course_name")
            if not course_id or not course_name:
                continue
            courses.append(
                CourseInfo(
                    course_id=str(course_id),
                    course_name=str(course_name),
                    teacher=item.get("teacher"),
                    semester=item.get("semester"),
                )
            )

        if courses:
            proposed_values["enrolled_courses"] = courses
            field_sources["enrolled_courses"] = source_system

    def _merge_credit_status_fragment(
        self,
        fragment: RawProfileFragment,
        school_code: str,
        proposed_values: dict[str, Any],
        field_sources: dict[str, str],
    ) -> None:
        structured = self._normalize_credit_status_payload(
            school_code=school_code,
            source_system=fragment.source_system,
            payload=fragment.payload,
            collected_at=fragment.collected_at,
        )
        proposed_values["credit_status"] = structured
        field_sources["credit_status"] = fragment.source_system

    def _merge_academic_completion_fragments(
        self,
        *,
        request: ProfileSyncRequest,
        fragments: dict[str, RawProfileFragment],
        proposed_values: dict[str, Any],
        field_sources: dict[str, str],
    ) -> None:
        overview_fragment = fragments.get("academic_completion_overview")
        nodes_fragment = fragments.get("academic_completion_nodes")
        courses_fragment = fragments.get("academic_completion_courses")

        overview_payload = overview_fragment.payload if overview_fragment else {}
        nodes_payload = nodes_fragment.payload if nodes_fragment else {}
        courses_payload = courses_fragment.payload if courses_fragment else {}

        context = overview_payload.get("context")
        if isinstance(context, dict):
            self._merge_identity_fragment(
                {
                    "student_id": context.get("student_id"),
                    "name": context.get("name"),
                    "college": context.get("college"),
                    "major": context.get("major"),
                    "grade": context.get("grade"),
                },
                overview_fragment.source_system if overview_fragment else "szu_ehall_academic_completion",
                proposed_values,
                field_sources,
            )

        source_system = self._first_non_empty_string(
            overview_fragment.source_system if overview_fragment else None,
            nodes_fragment.source_system if nodes_fragment else None,
            courses_fragment.source_system if courses_fragment else None,
        ) or "szu_ehall_academic_completion"
        synced_at = self._max_collected_at(
            fragment.collected_at for fragment in [overview_fragment, nodes_fragment, courses_fragment] if fragment
        )

        proposed_values["credit_status"] = self._build_academic_completion_credit_status(
            school_code=request.school_code,
            source_system=source_system,
            synced_at=synced_at,
            overview_payload=overview_payload,
            nodes_payload=nodes_payload,
            courses_payload=courses_payload,
        )
        field_sources["credit_status"] = source_system

    def _merge_hints(
        self,
        hints: dict[str, Any],
        school_code: str,
        proposed_values: dict[str, Any],
        field_sources: dict[str, str],
    ) -> None:
        for field_name in [
            "college",
            "major",
            "grade",
            "degree_level",
            "graduation_stage",
            "current_tasks",
            "identity_tags",
        ]:
            value = hints.get(field_name)
            normalized_value = self._normalize_identity_field(field_name, value)
            if normalized_value in (None, "", [], {}):
                continue
            proposed_values.setdefault(field_name, normalized_value)
            field_sources.setdefault(field_name, "request_hint")

        if hints.get("credit_status") not in (None, "", {}):
            proposed_values.setdefault(
                "credit_status",
                self._normalize_credit_status_payload(
                    school_code=school_code,
                    source_system="request_hint",
                    payload=hints["credit_status"],
                    collected_at=None,
                ),
            )
            field_sources.setdefault("credit_status", "request_hint")

        enrolled_courses = hints.get("enrolled_courses")
        if isinstance(enrolled_courses, list) and enrolled_courses:
            proposed_values.setdefault(
                "enrolled_courses",
                [CourseInfo.model_validate(course) for course in enrolled_courses],
            )
            field_sources.setdefault("enrolled_courses", "request_hint")

    def _apply_derivations(
        self,
        proposed_values: dict[str, Any],
        field_sources: dict[str, str],
    ) -> None:
        student_id = proposed_values.get("student_id")
        current_grade = self._normalize_grade(proposed_values.get("grade"))
        if current_grade:
            proposed_values["grade"] = current_grade
        elif isinstance(student_id, str):
            match = STUDENT_ID_GRADE_RE.match(student_id.strip())
            if match is not None:
                proposed_values["grade"] = match.group(1)
                field_sources["grade"] = "derived:student_id"

        current_degree = self._normalize_degree_level(proposed_values.get("degree_level"))
        if current_degree:
            proposed_values["degree_level"] = current_degree

        if "identity_tags" not in proposed_values and student_id:
            proposed_values["identity_tags"] = ["student"]
            field_sources["identity_tags"] = "derived:student_id"

    def _build_metadata(
        self,
        *,
        request: ProfileSyncRequest,
        sampling_result: ProfileSamplingResult,
        existing_profile: UserProfile | None,
        field_sources: dict[str, str],
    ) -> dict[str, Any]:
        metadata: dict[str, Any] = {}
        if existing_profile is not None:
            metadata.update(existing_profile.metadata)

        source_systems = sorted({fragment.source_system for fragment in sampling_result.fragments})
        metadata.update(
            {
                "source_school": request.school_code,
                "source_systems": source_systems,
                "last_synced_at": datetime.now(timezone.utc).isoformat(),
                "sync_mode": request.auth_mode,
                "field_provenance": field_sources,
                "sampling_metadata": sampling_result.metadata,
            }
        )
        return metadata

    def _collect_missing_fields(self, profile: UserProfile) -> list[str]:
        missing: list[str] = []
        for field_name in ["student_id", "name", "college", "major", "grade", "degree_level"]:
            if getattr(profile, field_name) in (None, ""):
                missing.append(field_name)
        if not profile.enrolled_courses:
            missing.append("enrolled_courses")
        return missing

    def _normalize_credit_status_payload(
        self,
        *,
        school_code: str,
        source_system: str,
        payload: dict[str, Any],
        collected_at: str | None,
    ) -> dict[str, Any]:
        if self._looks_like_structured_credit_status(payload):
            normalized = {
                "program_summary": dict(payload.get("program_summary", {})),
                "module_progress": list(payload.get("module_progress", [])),
                "pending_items": list(payload.get("pending_items", [])),
                "attention_signals": list(payload.get("attention_signals", [])),
                "source_snapshot": dict(payload.get("source_snapshot", {})),
            }
            snapshot = normalized["source_snapshot"]
            snapshot.setdefault("school_code", school_code)
            snapshot.setdefault("source_system", source_system)
            snapshot.setdefault("synced_at", collected_at)
            snapshot.setdefault("source_version", None)
            snapshot.setdefault("freshness_status", "fresh" if collected_at else "unknown")
            snapshot.setdefault("metadata", {})
            return normalized

        required_total = self._to_float(
            payload.get("required_total"),
            payload.get("totalCredit"),
            payload.get("required_total_credits"),
        )
        completed_total = self._to_float(
            payload.get("completed_total"),
            payload.get("getCredit"),
            payload.get("completed_total_credits"),
        )
        outstanding_total = self._to_float(
            payload.get("outstanding_total"),
            payload.get("needCredit"),
            payload.get("outstanding_total_credits"),
        )
        if outstanding_total is None and required_total is not None and completed_total is not None:
            outstanding_total = max(required_total - completed_total, 0.0)

        elective_batch = payload.get("elective_batch")
        if not isinstance(elective_batch, dict):
            elective_batch = payload.get("electiveBatch") if isinstance(payload.get("electiveBatch"), dict) else {}
        program_name = self._first_non_empty_string(
            payload.get("program_name"),
            elective_batch.get("name") if isinstance(elective_batch, dict) else None,
        )

        pending_items: list[dict[str, Any]] = []
        pending_core_courses = payload.get("pending_core_courses")
        if isinstance(pending_core_courses, list):
            for index, title in enumerate(pending_core_courses, start=1):
                title_text = self._first_non_empty_string(title)
                if not title_text:
                    continue
                pending_items.append(
                    {
                        "item_id": f"legacy_pending_core_{index}",
                        "item_type": "course_gap",
                        "title": title_text,
                        "module_id": None,
                        "module_name": None,
                        "credits": None,
                        "status": "pending",
                        "priority_hint": "medium",
                        "metadata": {},
                    }
                )

        attention_signals: list[dict[str, Any]] = []
        if outstanding_total not in (None, 0):
            attention_signals.append(
                {
                    "signal_type": "credit_gap",
                    "signal_key": "overall_credit_gap",
                    "signal_value": self._format_number(outstanding_total),
                    "severity": "high" if outstanding_total >= 6 else "medium",
                    "evidence": [f"仍缺 {self._format_number(outstanding_total)} 学分"],
                }
            )

        return {
            "program_summary": {
                "program_name": program_name,
                "required_total_credits": required_total,
                "completed_total_credits": completed_total,
                "outstanding_total_credits": outstanding_total,
                "exempted_total_credits": self._to_float(payload.get("exempted_total_credits")),
                "plan_version": self._extract_year_token(program_name),
            },
            "module_progress": [],
            "pending_items": pending_items,
            "attention_signals": attention_signals,
            "source_snapshot": {
                "school_code": school_code,
                "source_system": source_system,
                "synced_at": collected_at,
                "source_version": "legacy_credit_status_v1",
                "freshness_status": "fresh" if collected_at else "unknown",
                "metadata": {
                    "raw_credit_status": payload,
                },
            },
        }

    def _build_academic_completion_credit_status(
        self,
        *,
        school_code: str,
        source_system: str,
        synced_at: str | None,
        overview_payload: dict[str, Any],
        nodes_payload: dict[str, Any],
        courses_payload: dict[str, Any],
    ) -> dict[str, Any]:
        context = overview_payload.get("context") if isinstance(overview_payload.get("context"), dict) else {}
        overview = overview_payload.get("overview") if isinstance(overview_payload.get("overview"), dict) else {}
        plan_snapshots = overview_payload.get("plan_snapshots") if isinstance(overview_payload.get("plan_snapshots"), list) else []
        root_nodes = nodes_payload.get("root_nodes") if isinstance(nodes_payload.get("root_nodes"), list) else []
        child_nodes = nodes_payload.get("child_nodes") if isinstance(nodes_payload.get("child_nodes"), list) else []
        course_rows = courses_payload.get("course_rows") if isinstance(courses_payload.get("course_rows"), list) else []
        summary = courses_payload.get("summary") if isinstance(courses_payload.get("summary"), dict) else {}

        root_nodes_by_id = {
            self._first_non_empty_string(node.get("KZH")): node
            for node in root_nodes
            if isinstance(node, dict) and self._first_non_empty_string(node.get("KZH"))
        }

        module_progress: list[dict[str, Any]] = []
        module_progress_by_id: dict[str, dict[str, Any]] = {}

        for node in [*root_nodes, *child_nodes]:
            if not isinstance(node, dict):
                continue
            module_entry = self._build_module_progress_entry(node, root_nodes_by_id)
            if module_entry is None:
                continue
            module_progress.append(module_entry)
            module_progress_by_id[module_entry["module_id"]] = module_entry

        pending_items = self._build_pending_items(module_progress_by_id, course_rows)
        attention_signals = self._build_attention_signals(module_progress_by_id)

        required_total = self._to_float(context.get("required_credits"), overview.get("YQXF"))
        completed_total = self._to_float(context.get("completed_credits"), overview.get("WCXF"))
        outstanding_total = (
            max(required_total - completed_total, 0.0)
            if required_total is not None and completed_total is not None
            else None
        )

        return {
            "program_summary": {
                "program_name": self._first_non_empty_string(context.get("plan_name"), overview.get("PYFAMC")),
                "required_total_credits": required_total,
                "completed_total_credits": completed_total,
                "outstanding_total_credits": outstanding_total,
                "exempted_total_credits": self._to_float(overview.get("RDXF")),
                "plan_version": self._extract_year_token(context.get("plan_name"), overview.get("PYFAMC")),
            },
            "module_progress": module_progress,
            "pending_items": pending_items,
            "attention_signals": attention_signals,
            "source_snapshot": {
                "school_code": school_code,
                "source_system": source_system,
                "synced_at": synced_at,
                "source_version": "ehall_academic_completion_v1",
                "freshness_status": "fresh" if synced_at else "unknown",
                "metadata": {
                    "plan_id": self._first_non_empty_string(context.get("plan_id"), overview.get("PYFADM")),
                    "plan_name": self._first_non_empty_string(context.get("plan_name"), overview.get("PYFAMC")),
                    "by_njdm": overview_payload.get("by_njdm"),
                    "root_module_count": summary.get("root_module_count", len(root_nodes)),
                    "child_module_count": summary.get("child_module_count", len(child_nodes)),
                    "course_row_count": summary.get("course_row_count", len(course_rows)),
                    "plan_snapshot_count": len(plan_snapshots),
                },
            },
        }

    def _build_module_progress_entry(
        self,
        node: dict[str, Any],
        root_nodes_by_id: dict[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        module_id = self._first_non_empty_string(node.get("KZH"))
        if not module_id:
            return None

        parent_module_id = self._first_non_empty_string(node.get("FKZH"))
        if parent_module_id in (None, "-1"):
            parent_module_id = None
        parent_node = root_nodes_by_id.get(parent_module_id) if parent_module_id else None
        module_name = self._first_non_empty_string(node.get("KZM")) or module_id
        parent_module_name = self._first_non_empty_string(parent_node.get("KZM")) if isinstance(parent_node, dict) else None

        required_credits = self._to_float(node.get("YQXF"))
        completed_credits = self._to_float(node.get("WCXF"))
        outstanding_credits = self._compute_outstanding(required_credits, completed_credits)

        required_course_count = self._to_int(node.get("YQMS"))
        completed_course_count = self._to_int(node.get("WCMS"))
        outstanding_course_count = self._compute_outstanding_count(required_course_count, completed_course_count)

        completion_status = self._resolve_completion_status(
            required_credits=required_credits,
            completed_credits=completed_credits,
            outstanding_credits=outstanding_credits,
            required_course_count=required_course_count,
            completed_course_count=completed_course_count,
            outstanding_course_count=outstanding_course_count,
        )
        attention_tags = self._build_attention_tags(
            module_name=module_name,
            parent_module_name=parent_module_name,
            outstanding_credits=outstanding_credits,
            outstanding_course_count=outstanding_course_count,
        )

        return {
            "module_id": module_id,
            "module_name": module_name,
            "parent_module_id": parent_module_id,
            "parent_module_name": parent_module_name,
            "module_level": "child" if parent_module_id else "parent",
            "required_credits": required_credits,
            "completed_credits": completed_credits,
            "outstanding_credits": outstanding_credits,
            "required_course_count": required_course_count,
            "completed_course_count": completed_course_count,
            "outstanding_course_count": outstanding_course_count,
            "completion_status": completion_status,
            "attention_tags": attention_tags,
            "metadata": {
                "school_node_id": module_id,
                "school_parent_node_id": parent_module_id,
                "node_type": node.get("KZLXDM"),
                "course_category_code": node.get("KCLBDM"),
                "recognized_credits": self._to_float(node.get("RDXF")),
                "raw_node": {
                    key: value
                    for key, value in node.items()
                    if key in {"KZH", "FKZH", "KZM", "KZLXDM", "KCLBDM", "YQXF", "WCXF", "YQMS", "WCMS", "RDXF"}
                },
            },
        }

    def _build_pending_items(
        self,
        module_progress_by_id: dict[str, dict[str, Any]],
        course_rows: list[Any],
    ) -> list[dict[str, Any]]:
        rows_by_child_kzh: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in course_rows:
            if not isinstance(row, dict):
                continue
            child_kzh = self._first_non_empty_string(row.get("child_kzh"))
            if not child_kzh:
                continue
            rows_by_child_kzh[child_kzh].append(row)

        pending_items: list[dict[str, Any]] = []
        seen_item_ids: set[str] = set()

        for module_id, module in module_progress_by_id.items():
            if module.get("module_level") != "child":
                continue
            if module.get("completion_status") == "completed":
                continue

            pending_rows = [
                row for row in rows_by_child_kzh.get(module_id, []) if not self._is_course_completed(row)
            ]
            if pending_rows:
                for row in pending_rows:
                    course_id = self._first_non_empty_string(row.get("KCH"), row.get("course_id"), row.get("id"))
                    course_name = self._first_non_empty_string(row.get("KCM"), row.get("course_name"))
                    item_id = f"{module_id}:{course_id or course_name}"
                    if not course_name or item_id in seen_item_ids:
                        continue
                    seen_item_ids.add(item_id)
                    pending_items.append(
                        {
                            "item_id": item_id,
                            "item_type": self._resolve_pending_item_type(module),
                            "title": course_name,
                            "module_id": module_id,
                            "module_name": module.get("module_name"),
                            "credits": self._to_float(row.get("XF")),
                            "status": "pending",
                            "priority_hint": self._resolve_priority_hint(module),
                            "metadata": {
                                "course_id": course_id,
                                "parent_module_name": module.get("parent_module_name"),
                                "semester": self._first_non_empty_string(
                                    row.get("XNXQDM_DISPLAY"),
                                    row.get("XNXQDM"),
                                ),
                                "course_property": self._first_non_empty_string(row.get("KCXZDM_DISPLAY")),
                                "course_category": self._first_non_empty_string(row.get("KCLBDM_DISPLAY")),
                                "remark": row.get("BZ"),
                                "completion_display": row.get("SFTG_DISPLAY"),
                            },
                        }
                    )
                continue

            outstanding_credits = module.get("outstanding_credits")
            outstanding_course_count = module.get("outstanding_course_count")
            if outstanding_credits in (None, 0) and outstanding_course_count in (None, 0):
                continue

            item_id = f"{module_id}:module_gap"
            if item_id in seen_item_ids:
                continue
            seen_item_ids.add(item_id)
            pending_items.append(
                {
                    "item_id": item_id,
                    "item_type": "module_credit_gap",
                    "title": self._build_module_gap_title(module),
                    "module_id": module_id,
                    "module_name": module.get("module_name"),
                    "credits": outstanding_credits,
                    "status": "pending",
                    "priority_hint": self._resolve_priority_hint(module),
                    "metadata": {
                        "outstanding_course_count": outstanding_course_count,
                        "parent_module_name": module.get("parent_module_name"),
                    },
                }
            )

        return pending_items

    def _build_attention_signals(
        self,
        module_progress_by_id: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        signals: list[dict[str, Any]] = []

        for module in module_progress_by_id.values():
            if module.get("module_level") != "child":
                continue
            if module.get("completion_status") == "completed":
                continue

            outstanding_credits = module.get("outstanding_credits")
            outstanding_course_count = module.get("outstanding_course_count")
            if outstanding_credits in (None, 0) and outstanding_course_count in (None, 0):
                continue

            signal_type = self._resolve_signal_type(module)
            signal_key = self._resolve_signal_key(module, signal_type)
            signal_value = (
                self._format_number(outstanding_credits)
                if outstanding_credits not in (None, 0)
                else str(outstanding_course_count)
            )
            signals.append(
                {
                    "signal_type": signal_type,
                    "signal_key": signal_key,
                    "signal_value": signal_value,
                    "severity": self._resolve_signal_severity(module),
                    "evidence": self._build_signal_evidence(module),
                }
            )

        overall_gap = [
            module
            for module in module_progress_by_id.values()
            if module.get("completion_status") != "completed" and module.get("module_level") == "child"
        ]
        if overall_gap:
            signals.append(
                {
                    "signal_type": "credit_gap",
                    "signal_key": "overall_credit_gap",
                    "signal_value": str(len(overall_gap)),
                    "severity": "high" if len(overall_gap) >= 3 else "medium",
                    "evidence": [f"仍有 {len(overall_gap)} 个子模块未完成"],
                }
            )

        return signals

    @staticmethod
    def _looks_like_structured_credit_status(payload: dict[str, Any]) -> bool:
        return any(
            key in payload
            for key in ["program_summary", "module_progress", "pending_items", "attention_signals", "source_snapshot"]
        )

    def _normalize_identity_field(self, field_name: str, value: Any) -> Any:
        if field_name == "grade":
            return self._normalize_grade(value)
        if field_name == "degree_level":
            return self._normalize_degree_level(value)
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    def _normalize_grade(self, value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        stripped = value.strip()
        if not stripped:
            return None
        match = YEAR_TOKEN_RE.search(stripped)
        if match is not None:
            return match.group(1)
        return stripped

    def _normalize_degree_level(self, value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        stripped = value.strip()
        if not stripped:
            return None
        normalized = stripped.lower()
        mapping = {
            "本科": "undergraduate",
            "本科生": "undergraduate",
            "undergraduate": "undergraduate",
            "研究生": "graduate",
            "graduate": "graduate",
            "硕士": "master",
            "硕士研究生": "master",
            "master": "master",
            "博士": "doctor",
            "博士研究生": "doctor",
            "doctor": "doctor",
        }
        return mapping.get(stripped, mapping.get(normalized, stripped))

    @staticmethod
    def _to_float(*values: Any) -> float | None:
        for value in values:
            if value in (None, ""):
                continue
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _to_int(*values: Any) -> int | None:
        for value in values:
            if value in (None, ""):
                continue
            try:
                return int(float(value))
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _compute_outstanding(required: float | None, completed: float | None) -> float | None:
        if required is None:
            return None
        if completed is None:
            return required
        return max(required - completed, 0.0)

    @staticmethod
    def _compute_outstanding_count(required: int | None, completed: int | None) -> int | None:
        if required is None:
            return None
        if completed is None:
            return required
        return max(required - completed, 0)

    @staticmethod
    def _format_number(value: float | None) -> str | None:
        if value is None:
            return None
        if float(value).is_integer():
            return str(int(value))
        return f"{value:.1f}".rstrip("0").rstrip(".")

    def _resolve_completion_status(
        self,
        *,
        required_credits: float | None,
        completed_credits: float | None,
        outstanding_credits: float | None,
        required_course_count: int | None,
        completed_course_count: int | None,
        outstanding_course_count: int | None,
    ) -> str:
        has_gap = (outstanding_credits not in (None, 0)) or (outstanding_course_count not in (None, 0))
        if not has_gap:
            return "completed"

        has_progress = False
        if completed_credits not in (None, 0):
            has_progress = True
        if completed_course_count not in (None, 0):
            has_progress = True
        if required_credits in (None, 0) and required_course_count in (None, 0):
            has_progress = True
        return "in_progress" if has_progress else "not_started"

    def _build_attention_tags(
        self,
        *,
        module_name: str,
        parent_module_name: str | None,
        outstanding_credits: float | None,
        outstanding_course_count: int | None,
    ) -> list[str]:
        tags: list[str] = []
        if outstanding_credits not in (None, 0):
            tags.append("credit_gap")
        if outstanding_course_count not in (None, 0):
            tags.append("course_gap")

        combined = f"{parent_module_name or ''} {module_name}"
        if any(keyword in combined for keyword in ["创新", "创业", "讲座", "思政"]):
            tags.append("activity_based")
        if any(keyword in combined.lower() for keyword in ["网课", "慕课", "mooc", "在线", "平台"]):
            tags.append("online_platform")
        if any(keyword in combined for keyword in ["实践", "实习", "论文", "答辩", "毕业"]):
            tags.append("graduation_related")
            tags.append("practice_based")

        deduped: list[str] = []
        for tag in tags:
            if tag not in deduped:
                deduped.append(tag)
        return deduped

    @staticmethod
    def _is_course_completed(row: dict[str, Any]) -> bool:
        completion_display = str(row.get("SFTG_DISPLAY") or "").strip()
        return completion_display == "通过"

    def _resolve_pending_item_type(self, module: dict[str, Any]) -> str:
        tags = set(module.get("attention_tags", []))
        if "activity_based" in tags:
            return "activity_credit_opportunity"
        if "practice_based" in tags:
            return "practice_requirement"
        if "online_platform" in tags:
            return "online_platform_course"
        return "course_gap"

    def _resolve_priority_hint(self, module: dict[str, Any]) -> str:
        tags = set(module.get("attention_tags", []))
        if "graduation_related" in tags:
            return "high"
        if "activity_based" in tags or "online_platform" in tags:
            return "medium"
        return "low"

    def _resolve_signal_type(self, module: dict[str, Any]) -> str:
        tags = set(module.get("attention_tags", []))
        if "activity_based" in tags:
            return "activity_based_credit_gap"
        if "online_platform" in tags:
            return "online_platform_credit_gap"
        if "graduation_related" in tags:
            return "graduation_requirement_gap"
        if "practice_based" in tags:
            return "practice_credit_gap"
        return "credit_gap"

    def _resolve_signal_key(self, module: dict[str, Any], signal_type: str) -> str:
        module_name = str(module.get("module_name") or "")
        if "创新" in module_name or "创业" in module_name:
            return "innovation_credit_gap"
        if "实践" in module_name:
            return "practice_credit_gap"
        if "通识" in module_name:
            return "general_education_gap"
        return f"{self._slugify(module_name)}_{signal_type}"

    def _resolve_signal_severity(self, module: dict[str, Any]) -> str:
        tags = set(module.get("attention_tags", []))
        outstanding_credits = module.get("outstanding_credits") or 0
        outstanding_course_count = module.get("outstanding_course_count") or 0
        if "graduation_related" in tags or outstanding_course_count >= 2 or outstanding_credits >= 6:
            return "high"
        if "activity_based" in tags or "online_platform" in tags:
            return "medium"
        return "low"

    def _build_signal_evidence(self, module: dict[str, Any]) -> list[str]:
        evidence = [f"{module.get('module_name')} 未完成"]
        outstanding_credits = module.get("outstanding_credits")
        outstanding_course_count = module.get("outstanding_course_count")
        if outstanding_credits not in (None, 0):
            evidence.append(f"仍缺 {self._format_number(outstanding_credits)} 学分")
        if outstanding_course_count not in (None, 0):
            evidence.append(f"仍缺 {outstanding_course_count} 门")
        return evidence

    def _build_module_gap_title(self, module: dict[str, Any]) -> str:
        outstanding_credits = module.get("outstanding_credits")
        outstanding_course_count = module.get("outstanding_course_count")
        title = str(module.get("module_name") or "未完成模块")
        parts: list[str] = []
        if outstanding_credits not in (None, 0):
            parts.append(f"缺 {self._format_number(outstanding_credits)} 学分")
        if outstanding_course_count not in (None, 0):
            parts.append(f"缺 {outstanding_course_count} 门")
        if parts:
            return f"{title} 仍需补足 {' / '.join(parts)}"
        return title

    @staticmethod
    def _slugify(value: str) -> str:
        lowered = value.strip().lower()
        slug = re.sub(r"[^a-z0-9]+", "_", lowered)
        slug = slug.strip("_")
        return slug or "module"

    @staticmethod
    def _extract_year_token(*values: Any) -> str | None:
        for value in values:
            if not isinstance(value, str):
                continue
            match = YEAR_TOKEN_RE.search(value)
            if match is not None:
                return match.group(1)
        return None

    @staticmethod
    def _first_non_empty_string(*values: Any) -> str | None:
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _max_collected_at(values: Any) -> str | None:
        timestamps = [value for value in values if isinstance(value, str) and value.strip()]
        return max(timestamps) if timestamps else None
