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


class RuleConfig(BaseModel):
    rule_id: str
    rule_name: str
    scene: str
    enabled: bool = True
    priority: int = 0
    conditions: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    version: str


class RuleBundle(BaseModel):
    version: str
    ai_gate: dict[str, Any] = Field(default_factory=dict)
    thresholds: dict[str, Any] = Field(default_factory=dict)
    rules: list[RuleConfig] = Field(default_factory=list)


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
