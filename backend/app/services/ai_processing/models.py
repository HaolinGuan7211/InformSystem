from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ProfileFacet = Literal[
    "identity_core",
    "current_courses",
    "academic_completion",
    "graduation_progress",
    "activity_based_credit_gap",
    "online_platform_credit_gap",
    "custom_watch_items",
    "notification_preference",
]


class ProfileContext(BaseModel):
    user_id: str
    facets: list[ProfileFacet] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    generated_at: str


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
    required_profile_facets: list[ProfileFacet] = Field(default_factory=list)
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


class AIStage1Result(BaseModel):
    user_id: str
    relevance_hint_stage1: Literal["irrelevant", "candidate", "relevant"]
    required_profile_facets: list[ProfileFacet] = Field(default_factory=list)
    reason_summary_stage1: str | None = None
    confidence: float = 0.0
    generated_at: str


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
    enabled: bool = True
    provider: str = "mock"
    model_name: str
    prompt_version: str
    endpoint: str | None = None
    api_key: str | None = None
    timeout_seconds: float = 15.0
    max_retries: int = Field(default=0, ge=0)
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
