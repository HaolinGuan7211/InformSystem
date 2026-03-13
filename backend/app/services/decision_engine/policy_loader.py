from __future__ import annotations

from backend.app.services.decision_engine.policies import DecisionPolicyProvider, PushPolicyConfig


class PolicyLoader:
    def __init__(self, provider: DecisionPolicyProvider) -> None:
        self._provider = provider

    async def load_policies(self) -> list[PushPolicyConfig]:
        if hasattr(self._provider, "get_active_policies"):
            payload = await self._provider.get_active_policies()
        else:
            payload = await self._provider.get_push_policies()

        return [
            policy
            if isinstance(policy, PushPolicyConfig)
            else PushPolicyConfig.model_validate(
                policy.model_dump(mode="json") if hasattr(policy, "model_dump") else policy
            )
            for policy in payload
        ]
