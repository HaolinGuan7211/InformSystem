from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.app.services.profile_sampling.models import (
    ProfileSyncRequest,
    RawProfileFragment,
    SchoolSessionHandle,
)
from backend.app.services.profile_sampling.samplers.base import ProfileSampler
from backend.app.services.user_profile.models import CourseInfo


class SzuHintPayloadSampler(ProfileSampler):
    source_system = "szu_hint_payload"

    def supports(
        self,
        session_handle: SchoolSessionHandle,
        request: ProfileSyncRequest,
    ) -> bool:
        return any(
            key in request.hints
            for key in ["szu_personal_info", "szu_student_profile", "szu_selected_courses"]
        )

    async def sample(
        self,
        session_handle: SchoolSessionHandle,
        request: ProfileSyncRequest,
    ) -> list[RawProfileFragment]:
        fragments: list[RawProfileFragment] = []
        collected_at = datetime.now(timezone.utc).isoformat()

        personal_info = request.hints.get("szu_personal_info")
        if isinstance(personal_info, dict):
            payload = self._build_identity_from_personal_info(personal_info)
            if payload:
                fragments.append(
                    RawProfileFragment(
                        fragment_type="identity",
                        source_system="szu_personal_info_hint",
                        payload=payload,
                        collected_at=collected_at,
                    )
                )

        student_profile = request.hints.get("szu_student_profile")
        if isinstance(student_profile, dict):
            identity_payload = self._build_identity_from_student_profile(student_profile)
            if identity_payload:
                fragments.append(
                    RawProfileFragment(
                        fragment_type="identity",
                        source_system="szu_student_profile_hint",
                        payload=identity_payload,
                        collected_at=collected_at,
                    )
                )

            credit_payload = self._build_credit_status(student_profile)
            if credit_payload:
                fragments.append(
                    RawProfileFragment(
                        fragment_type="credit_status",
                        source_system="szu_student_profile_hint",
                        payload=credit_payload,
                        collected_at=collected_at,
                    )
                )

        selected_courses = request.hints.get("szu_selected_courses")
        course_payload = self._build_courses(selected_courses)
        if course_payload:
            fragments.append(
                RawProfileFragment(
                    fragment_type="courses",
                    source_system="szu_selected_courses_hint",
                    payload={"courses": course_payload},
                    collected_at=collected_at,
                )
            )

        return fragments

    def _build_identity_from_personal_info(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = payload.get("data", payload)
        account_setting = data.get("accountSetting", {}) if isinstance(data, dict) else {}
        student_id = self._first_string(
            data.get("uid"),
            data.get("id"),
            account_setting.get("id"),
            account_setting.get("userid"),
        )
        name = self._first_string(data.get("cn"), data.get("name"))

        result: dict[str, Any] = {}
        if student_id:
            result["student_id"] = student_id
        if name:
            result["name"] = name
        if isinstance(data.get("mobile"), str) and data["mobile"]:
            result["metadata"] = {"masked_mobile": data["mobile"]}
        return result

    def _build_identity_from_student_profile(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = payload.get("data", payload)
        result: dict[str, Any] = {}

        field_mapping = {
            "student_id": [
                data.get("studentId"),
                data.get("studentNumber"),
                data.get("number"),
                data.get("code"),
            ],
            "name": [data.get("name"), data.get("studentName")],
            "college": [data.get("collegeName"), data.get("departmentName"), data.get("college")],
            "major": [data.get("majorName"), data.get("professionalName"), data.get("major")],
            "grade": [data.get("grade"), data.get("gradeName")],
            "degree_level": [
                data.get("degreeLevel"),
                data.get("educationLevelName"),
                data.get("studentTypeName"),
                data.get("trainingLevel"),
            ],
        }

        for field_name, candidates in field_mapping.items():
            value = self._first_string(*candidates)
            if value:
                result[field_name] = value

        result["degree_level"] = self._normalize_degree_level(result.get("degree_level"))
        result["metadata"] = {
            key: value
            for key, value in {
                "campus": self._first_string(data.get("campusName"), data.get("campus")),
                "elective_batch_name": self._nested_string(data.get("electiveBatch"), "name"),
                "elective_batch_type": self._nested_string(data.get("electiveBatch"), "typeName"),
            }.items()
            if value
        }
        return {key: value for key, value in result.items() if value not in (None, "", {})}

    def _build_credit_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = payload.get("data", payload)
        keys = [
            "totalCredit",
            "getCredit",
            "needCredit",
            "getCreditProportion",
            "limitElective",
            "moocCredit",
            "electiveIsOpen",
        ]
        credit_status = {
            key: data.get(key)
            for key in keys
            if data.get(key) not in (None, "")
        }
        elective_batch = data.get("electiveBatch")
        if isinstance(elective_batch, dict):
            credit_status["elective_batch"] = {
                sub_key: elective_batch.get(sub_key)
                for sub_key in ["code", "name", "typeCode", "typeName", "beginTime", "endTime"]
                if elective_batch.get(sub_key) not in (None, "")
            }
        return credit_status

    def _build_courses(self, payload: Any) -> list[dict[str, Any]]:
        if payload in (None, "", {}):
            return []

        data_list = payload
        if isinstance(payload, dict):
            for key in ["dataList", "datas", "data", "rows", "list"]:
                value = payload.get(key)
                if isinstance(value, list):
                    data_list = value
                    break

        if not isinstance(data_list, list):
            return []

        courses: list[dict[str, Any]] = []
        for item in data_list:
            if not isinstance(item, dict):
                continue
            course_id = self._first_string(
                item.get("courseId"),
                item.get("courseNumber"),
                item.get("kch"),
                item.get("id"),
            )
            course_name = self._first_string(
                item.get("courseName"),
                item.get("kcmc"),
                item.get("name"),
            )
            if not course_id or not course_name:
                continue
            course = CourseInfo(
                course_id=course_id,
                course_name=course_name,
                teacher=self._first_string(item.get("teacherName"), item.get("jsxm"), item.get("teacher")),
                semester=self._first_string(item.get("semester"), item.get("semesterName"), item.get("xqm")),
            )
            courses.append(course.model_dump())
        return courses

    def _nested_string(self, payload: Any, key: str) -> str | None:
        if isinstance(payload, dict):
            return self._first_string(payload.get(key))
        return None

    def _normalize_degree_level(self, value: str | None) -> str | None:
        if not value:
            return None
        text = value.strip().lower()
        mapping = {
            "本科": "undergraduate",
            "本科生": "undergraduate",
            "undergraduate": "undergraduate",
            "研究生": "graduate",
            "硕士": "master",
            "硕士研究生": "master",
            "master": "master",
            "博士": "doctor",
            "博士研究生": "doctor",
            "doctor": "doctor",
        }
        return mapping.get(value.strip(), mapping.get(text, value.strip()))

    def _first_string(self, *values: Any) -> str | None:
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None
