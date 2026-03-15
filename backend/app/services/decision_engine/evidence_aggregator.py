from __future__ import annotations

from backend.app.shared.models import AIAnalysisResult, DecisionEvidence, RuleAnalysisResult, UserProfile


class EvidenceAggregator:
    async def aggregate(
        self,
        rule_result: RuleAnalysisResult,
        ai_result: AIAnalysisResult | None,
        user_profile: UserProfile,
        profile_signal_summary: dict[str, object] | None = None,
        decision_context: dict[str, object] | None = None,
    ) -> list[DecisionEvidence]:
        evidences = [
            DecisionEvidence(
                source="rule",
                key="relevance_status",
                value=rule_result.relevance_status,
            )
        ]

        has_ai_risk_hint = bool(ai_result and ai_result.risk_hint)
        if has_ai_risk_hint:
            evidences.append(
                DecisionEvidence(
                    source="ai",
                    key="risk_hint",
                    value=ai_result.risk_hint,
                )
            )

        if not has_ai_risk_hint and rule_result.deadline_at:
            evidences.append(
                DecisionEvidence(
                    source="rule",
                    key="deadline_at",
                    value=rule_result.deadline_at,
                )
            )

        ai_relevance_hint = str(ai_result.relevance_hint or "").strip() if ai_result else ""
        if ai_relevance_hint and ai_relevance_hint != "relevant":
            evidences.append(
                DecisionEvidence(
                    source="ai",
                    key="relevance_hint",
                    value=ai_relevance_hint,
                )
            )

        matched_attention = (profile_signal_summary or {}).get("matched_attention_signals", [])
        if matched_attention:
            top_signal = matched_attention[0]
            evidences.append(
                DecisionEvidence(
                    source="profile",
                    key="attention_signal",
                    value=str(top_signal.get("signal_key") or top_signal.get("signal_type") or "matched_signal"),
                )
            )

        matched_pending = (profile_signal_summary or {}).get("matched_pending_items", [])
        if matched_pending:
            top_pending = matched_pending[0]
            evidences.append(
                DecisionEvidence(
                    source="profile",
                    key="pending_item",
                    value=str(top_pending.get("item_id") or top_pending.get("title") or "matched_pending_item"),
                )
            )

        if not matched_attention and not matched_pending and (
            has_ai_risk_hint
            or rule_result.deadline_at
            or (
                ai_relevance_hint
                and ai_relevance_hint != "relevant"
                and (decision_context or {}).get("reason_code") in {
                    "ai_stage1_irrelevant",
                    "ai_stage2_irrelevant",
                    "ai_uncertain",
                }
            )
        ):
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
