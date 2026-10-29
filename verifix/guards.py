"""Deterministic guard rails around the agent's behaviour. No LLM here."""
from __future__ import annotations

from dataclasses import dataclass, field

HINTS = {
    "RECOVERED": "Independent verifier: recovered.",
    "PARTIAL": ("Partial improvement: this action helped, but some services are still unhealthy. "
                "Look for a second cause among unhealthy_services."),
    "DEGRADING": ("Services recovered briefly and then failed again, so the root cause persists. "
                  "A restart only clears transient state; look for a persistent cause "
                  "such as a bad deploy or a bad config."),
    "FAILED": "No measurable improvement: this action did not address the root cause.",
}


def signature(action: str, args: dict) -> tuple:
    """Identity of an action for repeat detection."""
    if action == "update_config":
        return (action, args.get("service"), args.get("key"), str(args.get("value")))
    return (action, args.get("service"))


@dataclass
class SessionState:
    deploys_checked: bool = False
    configs_checked: set = field(default_factory=set)
    tried: dict = field(default_factory=dict)   # signature -> verifier status

    def note_read(self, tool: str, args: dict) -> None:
        if tool == "get_recent_deploys":
            self.deploys_checked = True
        elif tool == "get_config" and args.get("service"):
            self.configs_checked.add(args["service"])

    def note_action(self, action: str, args: dict, status: str) -> None:
        self.tried[signature(action, args)] = status


def check_investigation(state: SessionState, service: str | None) -> str | None:
    missing = []
    if not state.deploys_checked:
        missing.append("get_recent_deploys")
    if service not in state.configs_checked:
        missing.append(f"get_config(service={service})")
    if missing:
        return ("Investigate before acting: you have not yet called " + " and ".join(missing)
                + ". Recent changes (deploys, config) are a common root cause. "
                  "Read them, then propose your action again.")
    return None


def check_repeat(state: SessionState, action: str, args: dict) -> str | None:
    status = state.tried.get(signature(action, args))
    if status is not None and status != "RECOVERED":
        return (f"You already executed {action} on {args.get('service')} and the independent "
                f"verifier reported {status}. Repeating it will not help. Choose a different "
                "action type or a different service, or call finish with escalate=true.")
    return None