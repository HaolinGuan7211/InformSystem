from __future__ import annotations

import sqlite3
from pathlib import Path


def get_connection(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def _table_columns(connection: sqlite3.Connection, table_name: str) -> set[str]:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {row["name"] for row in rows}


def _ensure_columns(
    connection: sqlite3.Connection,
    table_name: str,
    definitions: dict[str, str],
) -> None:
    existing = _table_columns(connection, table_name)
    for column_name, column_definition in definitions.items():
        if column_name in existing:
            continue
        connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )


def init_database(database_path: Path) -> None:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    with get_connection(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_profiles (
                user_id TEXT PRIMARY KEY,
                student_id TEXT NOT NULL UNIQUE,
                name TEXT,
                college TEXT,
                major TEXT,
                grade TEXT,
                degree_level TEXT,
                identity_tags_json TEXT NOT NULL DEFAULT '[]',
                graduation_stage TEXT,
                credit_status_json TEXT NOT NULL DEFAULT '{}',
                current_tasks_json TEXT NOT NULL DEFAULT '[]',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_profiles_college ON user_profiles (college)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_profiles_grade ON user_profiles (grade)"
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_user_profiles_graduation_stage
            ON user_profiles (graduation_stage)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_course_enrollments (
                user_id TEXT NOT NULL,
                course_id TEXT NOT NULL,
                course_name TEXT NOT NULL,
                teacher TEXT,
                semester TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(user_id, course_id, semester)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_course_enrollments_user_id ON user_course_enrollments (user_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_course_enrollments_semester ON user_course_enrollments (semester)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id TEXT PRIMARY KEY,
                channels_json TEXT NOT NULL DEFAULT '[]',
                quiet_hours_json TEXT NOT NULL DEFAULT '[]',
                digest_enabled INTEGER NOT NULL DEFAULT 1,
                muted_categories_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS source_configs (
                source_id TEXT PRIMARY KEY,
                source_name TEXT NOT NULL,
                source_type TEXT NOT NULL,
                connector_type TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                auth_config TEXT NOT NULL DEFAULT '{}',
                parse_config TEXT NOT NULL DEFAULT '{}',
                polling_schedule TEXT,
                authority_level TEXT,
                priority INTEGER NOT NULL DEFAULT 0,
                version TEXT,
                config_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS raw_events (
                event_id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_name TEXT NOT NULL,
                channel_type TEXT NOT NULL,
                title TEXT,
                content_text TEXT NOT NULL,
                content_html TEXT,
                author TEXT,
                published_at TEXT,
                collected_at TEXT NOT NULL,
                url TEXT,
                attachments_json TEXT NOT NULL DEFAULT '[]',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                canonical_notice_id TEXT,
                content_hash TEXT,
                unique_source_key TEXT
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_raw_events_source_id ON raw_events (source_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_raw_events_unique_source_key ON raw_events (unique_source_key)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_raw_events_url ON raw_events (url)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_raw_events_content_hash ON raw_events (content_hash)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS rule_configs (
                rule_id TEXT NOT NULL,
                version TEXT NOT NULL,
                rule_name TEXT NOT NULL,
                scene TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                priority INTEGER NOT NULL DEFAULT 0,
                conditions_json TEXT NOT NULL DEFAULT '{}',
                outputs_json TEXT NOT NULL DEFAULT '{}',
                config_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (rule_id, version)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_rule_configs_scene ON rule_configs (scene)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_rule_configs_enabled ON rule_configs (enabled)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_rule_configs_priority ON rule_configs (priority)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS rule_analysis_results (
                analysis_id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                rule_version TEXT NOT NULL,
                candidate_categories_json TEXT NOT NULL DEFAULT '[]',
                matched_rules_json TEXT NOT NULL DEFAULT '[]',
                extracted_signals_json TEXT NOT NULL DEFAULT '{}',
                relevance_status TEXT NOT NULL,
                relevance_score REAL NOT NULL,
                action_required INTEGER,
                deadline_at TEXT,
                urgency_level TEXT NOT NULL,
                risk_level TEXT NOT NULL,
                should_invoke_ai INTEGER NOT NULL,
                should_continue INTEGER NOT NULL,
                explanation_json TEXT NOT NULL DEFAULT '[]',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                generated_at TEXT NOT NULL,
                UNIQUE(event_id, user_id, rule_version)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_rule_results_event_id ON rule_analysis_results (event_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_rule_results_user_id ON rule_analysis_results (user_id)"
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_rule_results_relevance_status
            ON rule_analysis_results (relevance_status)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_rule_results_should_invoke_ai
            ON rule_analysis_results (should_invoke_ai)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_analysis_results (
                ai_result_id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                model_name TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                summary TEXT,
                normalized_category TEXT,
                action_items_json TEXT NOT NULL DEFAULT '[]',
                extracted_fields_json TEXT NOT NULL DEFAULT '[]',
                relevance_hint TEXT,
                urgency_hint TEXT,
                risk_hint TEXT,
                confidence REAL NOT NULL DEFAULT 0.0,
                needs_human_review INTEGER NOT NULL DEFAULT 0,
                raw_response_ref TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                generated_at TEXT NOT NULL,
                UNIQUE(event_id, user_id, model_name, prompt_version)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_analysis_results_event_id ON ai_analysis_results (event_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_analysis_results_user_id ON ai_analysis_results (user_id)"
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ai_analysis_results_needs_human_review
            ON ai_analysis_results (needs_human_review)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_call_logs (
                call_id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                model_name TEXT NOT NULL,
                prompt_version TEXT NOT NULL,
                status TEXT NOT NULL,
                latency_ms INTEGER,
                error_message TEXT,
                raw_request_ref TEXT,
                raw_response_ref TEXT,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_call_logs_event_id ON ai_call_logs (event_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_ai_call_logs_user_id ON ai_call_logs (user_id)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS push_policy_configs (
                policy_id TEXT NOT NULL,
                version TEXT NOT NULL,
                policy_name TEXT NOT NULL,
                enabled INTEGER NOT NULL,
                action TEXT NOT NULL,
                conditions_json TEXT NOT NULL DEFAULT '{}',
                channels_json TEXT NOT NULL DEFAULT '[]',
                config_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (policy_id, version)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_push_policy_configs_enabled ON push_policy_configs (enabled)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_push_policy_configs_action ON push_policy_configs (action)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS notification_category_configs (
                category_id TEXT PRIMARY KEY,
                category_name TEXT NOT NULL,
                parent_category TEXT,
                keywords_json TEXT NOT NULL DEFAULT '[]',
                enabled INTEGER NOT NULL DEFAULT 1,
                config_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS config_change_logs (
                change_id TEXT PRIMARY KEY,
                config_type TEXT NOT NULL,
                version TEXT NOT NULL,
                operator TEXT NOT NULL,
                action TEXT NOT NULL,
                payload_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_config_change_logs_lookup
            ON config_change_logs (config_type, version, created_at)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS decision_results (
                decision_id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                relevance_status TEXT NOT NULL,
                priority_score REAL NOT NULL,
                priority_level TEXT NOT NULL,
                decision_action TEXT NOT NULL,
                delivery_timing TEXT NOT NULL,
                delivery_channels_json TEXT NOT NULL DEFAULT '[]',
                action_required INTEGER,
                deadline_at TEXT,
                reason_summary TEXT NOT NULL,
                explanations_json TEXT NOT NULL DEFAULT '[]',
                evidences_json TEXT NOT NULL DEFAULT '[]',
                policy_version TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                generated_at TEXT NOT NULL,
                UNIQUE(event_id, user_id, policy_version)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_decision_results_event_id ON decision_results (event_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_decision_results_user_id ON decision_results (user_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_decision_results_action ON decision_results (decision_action)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_decision_results_priority_level ON decision_results (priority_level)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS delivery_logs (
                log_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                decision_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                channel TEXT NOT NULL,
                status TEXT NOT NULL,
                retry_count INTEGER NOT NULL DEFAULT 0,
                provider_message_id TEXT,
                error_message TEXT,
                delivered_at TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_delivery_logs_decision_id ON delivery_logs (decision_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_delivery_logs_task_id ON delivery_logs (task_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_delivery_logs_event_id ON delivery_logs (event_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_delivery_logs_user_id ON delivery_logs (user_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_delivery_logs_status ON delivery_logs (status)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_delivery_logs_channel ON delivery_logs (channel)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS delivery_digest_jobs (
                job_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                window_key TEXT NOT NULL,
                status TEXT NOT NULL,
                task_refs_json TEXT NOT NULL DEFAULT '[]',
                scheduled_at TEXT NOT NULL,
                sent_at TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(user_id, window_key)
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_delivery_digest_jobs_status ON delivery_digest_jobs (status)"
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_delivery_digest_jobs_scheduled_at
            ON delivery_digest_jobs (scheduled_at)
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_feedback (
                feedback_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                decision_id TEXT,
                delivery_log_id TEXT,
                feedback_type TEXT NOT NULL,
                rating INTEGER,
                comment TEXT,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_feedback_user_id ON user_feedback (user_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_feedback_event_id ON user_feedback (event_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_feedback_feedback_type ON user_feedback (feedback_type)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_feedback_created_at ON user_feedback (created_at)"
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS optimization_samples (
                sample_id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                rule_analysis_id TEXT,
                ai_result_id TEXT,
                decision_id TEXT,
                delivery_log_id TEXT,
                outcome_label TEXT NOT NULL,
                source TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                generated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_optimization_samples_event_id ON optimization_samples (event_id)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_optimization_samples_user_id ON optimization_samples (user_id)"
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_optimization_samples_outcome_label
            ON optimization_samples (outcome_label)
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_optimization_samples_source ON optimization_samples (source)"
        )
        _ensure_columns(
            connection,
            "source_configs",
            {
                "version": "TEXT",
                "config_json": "TEXT NOT NULL DEFAULT '{}'",
                "created_at": "TEXT NOT NULL DEFAULT ''",
                "updated_at": "TEXT NOT NULL DEFAULT ''",
            },
        )
        _ensure_columns(
            connection,
            "push_policy_configs",
            {
                "config_json": "TEXT NOT NULL DEFAULT '{}'",
                "created_at": "TEXT NOT NULL DEFAULT ''",
                "updated_at": "TEXT NOT NULL DEFAULT ''",
            },
        )
        connection.commit()
