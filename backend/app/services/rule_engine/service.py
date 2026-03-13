from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from backend.app.services.ingestion.models import SourceEvent
from backend.app.services.rule_engine.action_risk_evaluator import ActionRiskEvaluator
from backend.app.services.rule_engine.ai_trigger_gate import AITriggerGate
from backend.app.services.rule_engine.audience_matcher import AudienceMatcher
from backend.app.services.rule_engine.config_loader import RuleConfigLoader
from backend.app.services.rule_engine.models import MatchedRule, RuleAnalysisResult, RuleConfig
from backend.app.services.rule_engine.preprocessor import EventPreprocessor
from backend.app.services.rule_engine.repositories.rule_analysis_repository import RuleAnalysisRepository
from backend.app.services.rule_engine.signal_extractor import SignalExtractor
from backend.app.services.user_profile.models import UserProfile


@dataclass(slots=True)
class EvaluatedRule:
    rule: RuleConfig
    evidence: list[str]
    matched_rule: MatchedRule


class RuleEngineService:
    def __init__(
        self,
        config_loader: RuleConfigLoader,
        preprocessor: EventPreprocessor,
        signal_extractor: SignalExtractor,
        audience_matcher: AudienceMatcher,
        action_risk_evaluator: ActionRiskEvaluator,
        ai_trigger_gate: AITriggerGate,
        repository: RuleAnalysisRepository | None = None,
    ) -> None:
        self._config_loader = config_loader
        self._preprocessor = preprocessor
        self._signal_extractor = signal_extractor
        self._audience_matcher = audience_matcher
        self._action_risk_evaluator = action_risk_evaluator
        self._ai_trigger_gate = ai_trigger_gate
        self._repository = repository

    async def analyze(
        self,
        event: SourceEvent,
        user_profile: UserProfile,
        context: dict[str, Any] | None = None,
    ) -> RuleAnalysisResult:
        context = context or {}
        scene = context.get("scene", "rule_engine")
        bundle = await self._config_loader.load_bundle(scene)
        rule_version = context.get("rule_version", bundle.version)
        audience_matcher = AudienceMatcher(bundle.thresholds)
        ai_trigger_gate = AITriggerGate(bundle.ai_gate)

        rule_view = await self._preprocessor.build_rule_view(event)
        signals = await self._signal_extractor.extract(rule_view, bundle.rules)
        evaluated_rules = self._evaluate_rules(bundle.rules, signals, user_profile)
        self._inject_rule_signals(signals, bundle.rules, evaluated_rules)

        serialized_rules = [self._serialize_evaluated_rule(match) for match in evaluated_rules]
        audience_result = await audience_matcher.match(
            event=event,
            user_profile=user_profile,
            signals=signals,
            evaluated_rules=serialized_rules,
        )
        action_result = await self._action_risk_evaluator.evaluate(
            event=event,
            signals=signals,
            evaluated_rules=serialized_rules,
            relevance_status=audience_result["relevance_status"],
        )

        result = RuleAnalysisResult(
            analysis_id=self._build_analysis_id(event.event_id, user_profile.user_id, rule_version),
            event_id=event.event_id,
            user_id=user_profile.user_id,
            rule_version=rule_version,
            candidate_categories=self._merge_unique(
                audience_result["candidate_categories"],
                action_result["candidate_categories"],
            ),
            matched_rules=self._merge_rules(
                audience_result["matched_rules"],
                action_result["matched_rules"],
            ),
            extracted_signals=self._build_extracted_signals(signals),
            relevance_status=audience_result["relevance_status"],
            relevance_score=audience_result["relevance_score"],
            action_required=action_result["action_required"],
            deadline_at=action_result["deadline_at"],
            urgency_level=action_result["urgency_level"],
            risk_level=action_result["risk_level"],
            should_continue=action_result["should_continue"],
            explanation=self._merge_unique(
                audience_result["explanations"],
                action_result["explanations"],
            ),
            metadata={
                "idempotency_key": f"{event.event_id}:{user_profile.user_id}:{rule_version}",
                "matched_rule_count": len(evaluated_rules),
            },
            generated_at=context.get("generated_at", event.collected_at),
        )
        result.should_invoke_ai = await ai_trigger_gate.should_invoke_ai(result)

        if self._repository is not None:
            await self._repository.save(result)

        return result

    async def analyze_batch(
        self,
        events: list[SourceEvent],
        user_profile: UserProfile,
    ) -> list[RuleAnalysisResult]:
        return [await self.analyze(event, user_profile) for event in events]

    def _evaluate_rules(
        self,
        rules: list[RuleConfig],
        signals: dict[str, Any],
        user_profile: UserProfile,
    ) -> list[EvaluatedRule]:
        evaluated: list[EvaluatedRule] = []

        for rule in rules:
            hit = signals["rule_hits"].get(rule.rule_id, {})
            conditions = rule.conditions

            if conditions.get("all_keywords") and len(hit["matched_all"]) != len(conditions.get("all_keywords", [])):
                continue
            if conditions.get("any_keywords") and not hit["matched_any"]:
                continue
            if conditions.get("regex_patterns") and not hit["regex_matches"]:
                continue
            if conditions.get("requires_deadline") and not signals.get("deadline_text"):
                continue
            if conditions.get("requires_action") and not signals.get("action_keywords"):
                continue

            profile_match, profile_evidence = self._match_profile_conditions(conditions, user_profile)
            if conditions.get("profile_any") and not profile_match:
                continue

            evidence = self._build_evidence(hit, profile_evidence)
            matched_rule = MatchedRule(
                rule_id=rule.rule_id,
                rule_name=rule.rule_name,
                dimension=rule.outputs.get("dimension", "general"),
                hit_type=rule.outputs.get("hit_type", "keyword"),
                weight=float(rule.outputs.get("weight", 0.0)),
                evidence=evidence,
            )
            evaluated.append(EvaluatedRule(rule=rule, evidence=evidence, matched_rule=matched_rule))

        return evaluated

    def _match_profile_conditions(
        self,
        conditions: dict[str, Any],
        user_profile: UserProfile,
    ) -> tuple[bool, list[str]]:
        profile_any = conditions.get("profile_any", {})
        evidence: list[str] = []
        matched = False

        for field_name, expected_values in profile_any.items():
            field_value = getattr(user_profile, field_name, None)
            if field_value is None:
                continue

            if isinstance(field_value, list):
                hits = [value for value in expected_values if value in field_value]
            else:
                hits = [value for value in expected_values if value == field_value]

            if hits:
                matched = True
                evidence.extend(hits)

        return matched, self._dedupe_strings(evidence)

    def _build_evidence(self, hit: dict[str, Any], profile_evidence: list[str]) -> list[str]:
        evidence: list[str] = []
        for value in [*hit.get("matched_any", []), *hit.get("matched_all", []), *profile_evidence]:
            if value not in evidence:
                evidence.append(value)
        return evidence

    def _inject_rule_signals(
        self,
        signals: dict[str, Any],
        rules: list[RuleConfig],
        evaluated_rules: list[EvaluatedRule],
    ) -> None:
        audience_values: list[str] = []
        explicit_audience: list[str] = []
        action_keywords = list(signals.get("action_keywords", []))

        for rule in rules:
            signal_map = rule.outputs.get("signals", {})
            if signal_map.get("audience") and self._text_conditions_match(rule, signals):
                for value in signal_map.get("audience", []):
                    if value not in explicit_audience:
                        explicit_audience.append(value)

        for match in evaluated_rules:
            signal_map = match.rule.outputs.get("signals", {})
            for value in signal_map.get("audience", []):
                if value not in audience_values:
                    audience_values.append(value)
            for value in signal_map.get("action_keywords", []):
                if value not in action_keywords:
                    action_keywords.append(value)

        signals["audience"] = audience_values
        signals["explicit_audience"] = explicit_audience
        signals["action_keywords"] = action_keywords

    def _text_conditions_match(self, rule: RuleConfig, signals: dict[str, Any]) -> bool:
        hit = signals["rule_hits"].get(rule.rule_id, {})
        conditions = rule.conditions

        if conditions.get("all_keywords") and len(hit["matched_all"]) != len(conditions.get("all_keywords", [])):
            return False
        if conditions.get("any_keywords") and not hit["matched_any"]:
            return False
        if conditions.get("regex_patterns") and not hit["regex_matches"]:
            return False
        if conditions.get("requires_deadline") and not signals.get("deadline_text"):
            return False
        if conditions.get("requires_action") and not signals.get("action_keywords"):
            return False
        return True

    def _build_extracted_signals(self, signals: dict[str, Any]) -> dict[str, Any]:
        extracted: dict[str, Any] = {}
        if signals.get("audience"):
            extracted["audience"] = signals["audience"]
        if signals.get("action_keywords"):
            extracted["action_keywords"] = signals["action_keywords"]
        if signals.get("deadline_text"):
            extracted["deadline_text"] = signals["deadline_text"]
        return extracted

    def _serialize_evaluated_rule(self, match: EvaluatedRule) -> dict[str, Any]:
        return {"rule": match.rule, "matched_rule": match.matched_rule}

    def _merge_unique(self, left: list[str], right: list[str]) -> list[str]:
        result: list[str] = []
        for value in [*left, *right]:
            if value not in result:
                result.append(value)
        return result

    def _merge_rules(self, left: list[MatchedRule], right: list[MatchedRule]) -> list[MatchedRule]:
        result: list[MatchedRule] = []
        seen: set[str] = set()
        for value in [*left, *right]:
            if value.rule_id in seen:
                continue
            result.append(value)
            seen.add(value.rule_id)
        return result

    def _build_analysis_id(self, event_id: str, user_id: str, rule_version: str) -> str:
        digest = hashlib.sha1(f"{event_id}:{user_id}:{rule_version}".encode("utf-8")).hexdigest()
        return f"rule_{digest[:12]}"

    def _dedupe_strings(self, values: list[str]) -> list[str]:
        result: list[str] = []
        for value in values:
            if value and value not in result:
                result.append(value)
        return result
