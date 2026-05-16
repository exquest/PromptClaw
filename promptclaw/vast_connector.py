from __future__ import annotations

from dataclasses import dataclass


VAST_LIFECYCLE_ACTIONS: tuple[str, ...] = ("rent", "destroy", "start", "stop")


@dataclass(frozen=True)
class VastConnectorBoundary:
    provider: str = "vast"
    status: str = "stubbed"
    reason: str = (
        "Vast lifecycle operations are intentionally unavailable in the default "
        "PromptClaw PAL action registry."
    )
    blocked_actions: tuple[str, ...] = VAST_LIFECYCLE_ACTIONS
    callable_actions: tuple[str, ...] = ()

    def callable_action_names(self) -> tuple[str, ...]:
        return self.callable_actions

    def blocked_action_names(self) -> tuple[str, ...]:
        return self.blocked_actions

    def is_action_callable(self, action_name: str) -> bool:
        normalized = action_name.strip().lower()
        return normalized in self.callable_actions

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "status": self.status,
            "reason": self.reason,
            "blocked_actions": list(self.blocked_actions),
            "callable_actions": list(self.callable_actions),
        }


def default_vast_connector_boundary() -> VastConnectorBoundary:
    return VastConnectorBoundary()
