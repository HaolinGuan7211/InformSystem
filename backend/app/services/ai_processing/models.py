from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CourseInfo(BaseModel):
    course_id: str | None = None
    course_name: str | None = None
    teacher_name: str | None = None
    schedule_text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NotificationPreference(BaseModel):
    channels: list[str] = Field(default_factory=list)
    quiet_hours: list[str] = Field(default_factory=list)
    digest_enabled: bool = False
    muted_categories: list[str] = Field(default_factory=list)


class UserProfile(BaseModel):
    user_id: str
    student_id: str
    name: str | None = None
    college: str | None = None
    major: str | None = None
    grade: str | None = None
    degree_level: str | None = None
    identity_tags: list[str] = Field(default_factory=list)
    graduation_stage: str | None = None
    enrolled_courses: list[CourseInfo] = Field(default_factory=list)
    credit_status: dict[str, Any] = Field(default_factory=dict)
    current_tasks: list[str] = Field(default_factory=list)
    notification_preference: NotificationPreference = Field(default_factory=NotificationPreference)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MatchedRule(BaseModel):
    rule_id: str
    rule_name: str
    dimension: str
    hit_type: str
    weight: float = 0.0
    evidence: list[str] = Field(default_factory=list)


class RuleAnalysisResult(BaseModel):
    analysis_id: str
    event_id: str
    user_id: str
    rule_version: str
    candidate_categories: list[str] = Field(default_factory=list)
    matched_rules: list[MatchedRule] = Field(default_factory=list)
    extracted_signals: dict[str, Any] = Field(default_factory=dict)
    relevance_status: str
    relevance_score: float
    action_required: bool | None = None
    deadline_at: str | None = None
    urgency_level: str = "low"
    risk_level: str = "low"
    should_invoke_ai: bool = False
    should_continue: bool = True
    explanation: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    generated_at: str


class AIExtractedField(BaseModel):
    field_name: str
    field_value: Any
    confidence: float = 0.0


class AIAnalysisResult(BaseModel):
    ai_result_id: str
    event_id: str
    user_id: str
    model_name: str
    prompt_version: str
    summary: str | None = None
    normalized_category: str | None = None
    action_items: list[str] = Field(default_factory=list)
    extracted_fields: list[AIExtractedField] = Field(default_factory=list)
    relevance_hint: str | None = None
    urgency_hint: str | None = None
    risk_hint: str | None = None
    confidence: float = 0.0
    needs_human_review: bool = False
    raw_response_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    generated_at: str


class AIModelConfig(BaseModel):
    provider: str = "mock"
    model_name: str
    prompt_version: str
    endpoint: str | None = None
    api_key: str | None = None
    timeout_seconds: float = 15.0
    max_retries: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class GatewayResponse(BaseModel):
    provider: str = "mock"
    model_name: str
    content: dict[str, Any] | str | None = None
    raw_request_ref: str | None = None
    raw_response_ref: str | None = None
    latency_ms: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AICallLog(BaseModel):
    call_id: str
    event_id: str
    user_id: str
    model_name: str
    prompt_version: str
    status: str
    latency_ms: int | None = None
    error_message: str | None = None
    raw_request_ref: str | None = None
    raw_response_ref: str | None = None
    created_at: str
