from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.app.services.user_profile.models import UserProfile
from backend.app.shared.models import DecisionAction, PriorityLevel, RelevanceStatus


class ProbePersona(BaseModel):
    persona_id: str
    label: str
    description: str | None = None
    profile: UserProfile


class ProbePersonaOutcome(BaseModel):
    persona_id: str
    label: str
    user_id: str
    relevance_status: RelevanceStatus
    relevance_score: float
    decision_action: DecisionAction
    priority_level: PriorityLevel
    priority_score: float
    candidate_categories: list[str] = Field(default_factory=list)
    matched_rule_ids: list[str] = Field(default_factory=list)
    should_invoke_ai: bool = False
    ai_category: str | None = None
    ai_summary: str | None = None
    delivery_statuses: list[str] = Field(default_factory=list)
    reason_summary: str
    usefulness_score: float
    useful: bool
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProbeEventReport(BaseModel):
    event_id: str
    title: str | None = None
    published_at: str | None = None
    url: str | None = None
    source_name: str
    top_usefulness_score: float = 0.0
    useful: bool = False
    top_persona_id: str | None = None
    top_persona_label: str | None = None
    top_decision_action: DecisionAction | None = None
    top_priority_level: PriorityLevel | None = None
    top_reason_summary: str | None = None
    persona_outcomes: list[ProbePersonaOutcome] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


class BatchProbeReport(BaseModel):
    source_id: str
    source_name: str
    raw_item_count: int
    accepted_event_count: int
    dropped_event_count: int
    persona_count: int
    useful_event_count: int
    generated_at: str
    events: list[ProbeEventReport] = Field(default_factory=list)
