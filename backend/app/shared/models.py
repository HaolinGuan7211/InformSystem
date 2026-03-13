from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

RelevanceStatus = Literal["relevant", "irrelevant", "unknown"]
UrgencyLevel = Literal["low", "medium", "high", "critical"]
RiskLevel = Literal["low", "medium", "high", "critical"]
PriorityLevel = Literal["low", "medium", "high", "critical"]
DecisionAction = Literal["push_now", "push_high", "digest", "archive", "ignore"]
DeliveryTiming = Literal["immediate", "scheduled", "digest_window"]
DeliveryStatus = Literal["pending", "sent", "failed", "skipped"]
FeedbackType = Literal["useful", "not_relevant", "too_late", "too_frequent", "missed_important"]


class AttachmentInfo(BaseModel):
    name: str
    url: str | None = None
    mime_type: str | None = None
    storage_key: str | None = None


class SourceEvent(BaseModel):
    event_id: str
    source_id: str
    source_type: str
    source_name: str
    channel_type: str
    title: str | None = None
    content_text: str
    content_html: str | None = None
    author: str | None = None
    published_at: str | None = None
    collected_at: str
    url: str | None = None
    attachments: list[AttachmentInfo] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CourseInfo(BaseModel):
    course_id: str
    course_name: str
    teacher: str | None = None
    semester: str | None = None


class NotificationPreference(BaseModel):
    channels: list[str] = Field(default_factory=list)
    quiet_hours: list[str] = Field(default_factory=list)
    digest_enabled: bool = True
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
    relevance_status: RelevanceStatus
    relevance_score: float
    action_required: bool | None = None
    deadline_at: str | None = None
    urgency_level: UrgencyLevel = "low"
    risk_level: RiskLevel = "low"
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


class DecisionEvidence(BaseModel):
    source: str
    key: str
    value: str


class DecisionResult(BaseModel):
    decision_id: str
    event_id: str
    user_id: str
    relevance_status: RelevanceStatus
    priority_score: float
    priority_level: PriorityLevel
    decision_action: DecisionAction
    delivery_timing: DeliveryTiming
    delivery_channels: list[str] = Field(default_factory=list)
    action_required: bool | None = None
    deadline_at: str | None = None
    reason_summary: str
    explanations: list[str] = Field(default_factory=list)
    evidences: list[DecisionEvidence] = Field(default_factory=list)
    policy_version: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    generated_at: str


class DeliveryTask(BaseModel):
    task_id: str
    decision_id: str
    event_id: str
    user_id: str
    action: DecisionAction
    channel: str
    title: str
    body: str
    scheduled_at: str | None = None
    dedupe_key: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeliveryLog(BaseModel):
    log_id: str
    task_id: str
    decision_id: str
    event_id: str
    user_id: str
    channel: str
    status: DeliveryStatus
    retry_count: int = 0
    provider_message_id: str | None = None
    error_message: str | None = None
    delivered_at: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class UserFeedbackRecord(BaseModel):
    feedback_id: str
    user_id: str
    event_id: str
    decision_id: str | None = None
    delivery_log_id: str | None = None
    feedback_type: FeedbackType
    rating: int | None = Field(default=None, ge=1, le=5)
    comment: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class OptimizationSample(BaseModel):
    sample_id: str
    event_id: str
    user_id: str
    rule_analysis_id: str | None = None
    ai_result_id: str | None = None
    decision_id: str | None = None
    delivery_log_id: str | None = None
    outcome_label: str
    source: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    generated_at: str
