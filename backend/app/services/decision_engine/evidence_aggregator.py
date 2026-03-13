from __future__ import annotations

from backend.app.shared.models import AIAnalysisResult, DecisionEvidence, RuleAnalysisResult, UserProfile


class EvidenceAggregator:
    async def aggregate(
        self,
        rule_result: RuleAnalysisResult,
        ai_result: AIAnalysisResult | None,
        user_profile: UserProfile,
    ) -> list[DecisionEvidence]:
        evidences = [
            DecisionEvidence(
                source="rule",
                key="relevance_status",
                value=rule_result.relevance_status,
            )
        ]

        if ai_result and ai_result.risk_hint:
            evidences.append(
                DecisionEvidence(
                    source="ai",
                    key="risk_hint",
                    value=ai_result.risk_hint,
                )
            )
            return evidences

        if rule_result.deadline_at:
            evidences.append(
                DecisionEvidence(
                    source="rule",
                    key="deadline_at",
                    value=rule_result.deadline_at,
                )
            )
            return evidences

        matched_audiences = set(rule_result.extracted_signals.get("audience", []))
        matched_identity = next(
            (tag for tag in user_profile.identity_tags if tag in matched_audiences),
            None,
        )
        if matched_identity:
            evidences.append(
                DecisionEvidence(
                    source="profile",
                    key="identity_tag",
                    value=matched_identity,
                )
            )

        return evidences
