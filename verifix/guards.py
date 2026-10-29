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
    history: list = field(default_factory=list)  # every executed action's verifier status, in order

    def note_read(self, tool: str, args: dict) -> None:
        if tool == "get_recent_deploys":
            self.deploys_checked = True
        elif tool == "get_config" and args.get("service"):
            self.configs_checked.add(args["service"])

    def note_action(self, action: str, args: dict, status: str) -> None:
        self.tried[signature(action, args)] = status
        self.history.append(status)


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


FUTILITY_LIMIT = 4


def check_futility(state: SessionState, limit: int = FUTILITY_LIMIT) -> str | None:
    """Stop flailing: after `limit` executed actions with no improvement, force escalation."""
    statuses = state.history
    if len(statuses) >= limit and not any(s in ("PARTIAL", "RECOVERED") for s in statuses):
        return (f"{len(statuses)} executed actions produced no measurable improvement. "
                "Further actions are blocked. The root cause is probably outside what you can "
                "fix with the available actions. Call finish with escalate=true and explain your findings.")
    return None


def check_repeat(state: SessionState, action: str, args: dict) -> str | None:
    status = state.tried.get(signature(action, args))
    if status is not None and status != "RECOVERED":
        return (f"You already executed {action} on {args.get('service')} and the independent "
                f"verifier reported {status}. Repeating it will not help. Choose a different "
                "action type or a different service, or call finish with escalate=true.")
    return None