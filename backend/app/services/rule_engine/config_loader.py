from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from backend.app.services.rule_engine.models import RuleBundle


class RuleConfigLoader:
    def __init__(self, config_source: Path | Any) -> None:
        self._provider = config_source if hasattr(config_source, "get_rule_bundle") else None
        self._config_path = None if self._provider is not None else Path(config_source)

    async def load_bundle(self, scene: str | None = None) -> RuleBundle:
        if self._provider is not None:
            payload = await self._provider.get_rule_bundle(scene)
            if hasattr(payload, "model_dump"):
                return RuleBundle.model_validate(payload.model_dump(mode="json"))
            return RuleBundle.model_validate(payload)

        with self._config_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)

        bundle = RuleBundle.model_validate(payload)
        filtered_rules = [
            rule
            for rule in bundle.rules
            if rule.enabled and (scene is None or rule.scene == scene)
        ]
        filtered_rules.sort(key=lambda rule: (-rule.priority, rule.rule_id))
        return RuleBundle(
            version=bundle.version,
            ai_gate=bundle.ai_gate,
            thresholds=bundle.thresholds,
            rules=filtered_rules,
        )

    async def load_rules(self, scene: str | None = None):
        return (await self.load_bundle(scene)).rules
