from __future__ import annotations

from pydantic import BaseModel, Field

from backend.app.shared.models import (
    AIAnalysisResult,
    DecisionResult,
    DeliveryLog,
    RuleAnalysisResult,
    SourceEvent,
    UserProfile,
)


class WorkflowUserRun(BaseModel):
    user_profile: UserProfile
    rule_result: RuleAnalysisResult
    ai_result: AIAnalysisResult | None = None
    decision_result: DecisionResult
    delivery_logs: list[DeliveryLog] = Field(default_factory=list)


class WorkflowUserError(BaseModel):
    user_id: str
    stage: str
    error_message: str


class WorkflowRunResult(BaseModel):
    event: SourceEvent
    total_candidate_users: int
    processed_user_count: int
    skipped_user_ids: list[str] = Field(default_factory=list)
    errors: list[WorkflowUserError] = Field(default_factory=list)
    results: list[WorkflowUserRun] = Field(default_factory=list)
