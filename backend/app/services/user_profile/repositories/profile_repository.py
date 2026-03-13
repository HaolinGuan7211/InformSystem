from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.app.core.database import get_connection
from backend.app.services.user_profile.models import CourseInfo, NotificationPreference, UserProfile


class SQLiteUserProfileRepository:
    def __init__(self, database_path: Path, timezone_offset: str = "+08:00") -> None:
        self.database_path = database_path
        self._timezone_offset = timezone_offset

    async def save(self, profile: UserProfile) -> None:
        timestamp = self._default_timestamp()
        with get_connection(self.database_path) as connection:
            created_at = self._get_created_at(connection, "user_profiles", "user_id", profile.user_id) or timestamp
            connection.execute(
                """
                INSERT INTO user_profiles (
                    user_id,
                    student_id,
                    name,
                    college,
                    major,
                    grade,
                    degree_level,
                    identity_tags_json,
                    graduation_stage,
                    credit_status_json,
                    current_tasks_json,
                    metadata_json,
                    created_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    student_id = excluded.student_id,
                    name = excluded.name,
                    college = excluded.college,
                    major = excluded.major,
                    grade = excluded.grade,
                    degree_level = excluded.degree_level,
                    identity_tags_json = excluded.identity_tags_json,
                    graduation_stage = excluded.graduation_stage,
                    credit_status_json = excluded.credit_status_json,
                    current_tasks_json = excluded.current_tasks_json,
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    profile.user_id,
                    profile.student_id,
                    profile.name,
                    profile.college,
                    profile.major,
                    profile.grade,
                    profile.degree_level,
                    json.dumps(profile.identity_tags, ensure_ascii=False),
                    profile.graduation_stage,
                    json.dumps(profile.credit_status, ensure_ascii=False),
                    json.dumps(profile.current_tasks, ensure_ascii=False),
                    json.dumps(profile.metadata, ensure_ascii=False),
                    created_at,
                    timestamp,
                ),
            )
            self._replace_courses(connection, profile.user_id, profile.enrolled_courses, timestamp)
            self._upsert_preference(connection, profile.user_id, profile.notification_preference, timestamp)
            connection.commit()

    async def get_by_user_id(self, user_id: str) -> UserProfile | None:
        base_profile = await self.get_base_profile(user_id)
        if base_profile is None:
            return None

        return base_profile.model_copy(
            update={
                "enrolled_courses": await self.list_courses(user_id),
                "notification_preference": await self.get_preference(user_id),
            }
        )

    async def get_base_profile(self, user_id: str) -> UserProfile | None:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM user_profiles
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()
        return self._row_to_base_profile(row) if row else None

    async def list_profile_refs(self, limit: int = 1000) -> list[UserProfile]:
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM user_profiles
                ORDER BY updated_at DESC, user_id ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [self._row_to_base_profile(row) for row in rows]

    async def list_courses(self, user_id: str) -> list[CourseInfo]:
        with get_connection(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT course_id, course_name, teacher, semester
                FROM user_course_enrollments
                WHERE user_id = ?
                ORDER BY
                    CASE WHEN semester IS NULL THEN 1 ELSE 0 END,
                    semester DESC,
                    course_id ASC
                """,
                (user_id,),
            ).fetchall()

        return [
            CourseInfo(
                course_id=row["course_id"],
                course_name=row["course_name"],
                teacher=row["teacher"],
                semester=row["semester"],
            )
            for row in rows
        ]

    async def get_preference(self, user_id: str) -> NotificationPreference:
        with get_connection(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM user_preferences
                WHERE user_id = ?
                """,
                (user_id,),
            ).fetchone()

        if row is None:
            return NotificationPreference()

        return NotificationPreference(
            channels=self._load_json(row["channels_json"], []),
            quiet_hours=self._load_json(row["quiet_hours_json"], []),
            digest_enabled=bool(row["digest_enabled"]),
            muted_categories=self._load_json(row["muted_categories_json"], []),
        )

    def _row_to_base_profile(self, row) -> UserProfile:
        return UserProfile(
            user_id=row["user_id"],
            student_id=row["student_id"],
            name=row["name"],
            college=row["college"],
            major=row["major"],
            grade=row["grade"],
            degree_level=row["degree_level"],
            identity_tags=self._load_json(row["identity_tags_json"], []),
            graduation_stage=row["graduation_stage"],
            enrolled_courses=[],
            credit_status=self._load_json(row["credit_status_json"], {}),
            current_tasks=self._load_json(row["current_tasks_json"], []),
            notification_preference=NotificationPreference(),
            metadata=self._load_json(row["metadata_json"], {}),
        )

    def _replace_courses(self, connection, user_id: str, courses: list[CourseInfo], timestamp: str) -> None:
        connection.execute("DELETE FROM user_course_enrollments WHERE user_id = ?", (user_id,))
        if not courses:
            return

        connection.executemany(
            """
            INSERT INTO user_course_enrollments (
                user_id,
                course_id,
                course_name,
                teacher,
                semester,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    user_id,
                    course.course_id,
                    course.course_name,
                    course.teacher,
                    course.semester,
                    timestamp,
                    timestamp,
                )
                for course in courses
            ],
        )

    def _upsert_preference(
        self,
        connection,
        user_id: str,
        preference: NotificationPreference,
        timestamp: str,
    ) -> None:
        created_at = self._get_created_at(connection, "user_preferences", "user_id", user_id) or timestamp
        connection.execute(
            """
            INSERT INTO user_preferences (
                user_id,
                channels_json,
                quiet_hours_json,
                digest_enabled,
                muted_categories_json,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                channels_json = excluded.channels_json,
                quiet_hours_json = excluded.quiet_hours_json,
                digest_enabled = excluded.digest_enabled,
                muted_categories_json = excluded.muted_categories_json,
                updated_at = excluded.updated_at
            """,
            (
                user_id,
                json.dumps(preference.channels, ensure_ascii=False),
                json.dumps(preference.quiet_hours, ensure_ascii=False),
                int(preference.digest_enabled),
                json.dumps(preference.muted_categories, ensure_ascii=False),
                created_at,
                timestamp,
            ),
        )

    def _get_created_at(self, connection, table_name: str, key_field: str, key_value: str) -> str | None:
        row = connection.execute(
            f"SELECT created_at FROM {table_name} WHERE {key_field} = ?",
            (key_value,),
        ).fetchone()
        return row["created_at"] if row else None

    def _load_json(self, payload: str | None, default):
        if payload in (None, ""):
            return default
        return json.loads(payload)

    def _default_timestamp(self) -> str:
        offset = self._parse_timezone_offset(self._timezone_offset)
        return datetime.now(timezone.utc).astimezone(offset).isoformat()

    def _parse_timezone_offset(self, value: str) -> timezone:
        sign = 1 if value.startswith("+") else -1
        hour_text, minute_text = value[1:].split(":", maxsplit=1)
        delta = timedelta(hours=int(hour_text), minutes=int(minute_text))
        return timezone(sign * delta)
