"""Deterministic Policy Gate. Decides ALLOW / NEEDS_APPROVAL / DENY for every action.

No LLM. The agent can be fooled by a log line; this gate cannot.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from verifix.simulator import SERVICES

ALLOWED_ACTIONS = {
    "restart_service",
    "rollback_deploy",
    "scale_service",
    "update_config",
}

# Always needs a human.
HIGH_RISK_ACTIONS = {"update_config"}
# Restarting these is high-impact (data layer), so also needs a human.
PROTECTED_SERVICES = {"database"}

MAX_REPLICAS = 10
ALLOWED_CONFIG_KEYS = {"max_connections", "timeout_ms"}

INJECTION_PATTERNS = [
    r"ignore (all |any )?(previous|prior) instructions",
    r"disregard (the )?(above|previous)",
    r"you are now",
    r"system prompt",
    r"delete (the )?(database|all|everything)",
    r"drop table",
    r"rm -rf",
]


@dataclass
class Decision:
    verdict: str          # ALLOW | NEEDS_APPROVAL | DENY
    reason: str


def contains_injection(text: str) -> bool:
    t = text.lower()
    return any(re.search(p, t) for p in INJECTION_PATTERNS)


def evaluate_action(action: str, args: dict, evidence: list[str] | None = None) -> Decision:
    """Check one proposed action. `evidence` = log lines the agent cited as justification."""
    if action not in ALLOWED_ACTIONS:
        return Decision("DENY", f"action '{action}' is not in the allowed list")

    service = args.get("service")
    if service not in SERVICES:
        return Decision("DENY", f"unknown service '{service}'")

    if evidence:
        for line in evidence:
            if contains_injection(line):
                return Decision("DENY", "cited evidence contains a suspected prompt-injection pattern")

    if action == "scale_service":
        r = args.get("replicas")
        if not isinstance(r, int) or r < 1 or r > MAX_REPLICAS:
            return Decision("DENY", f"replicas must be an integer 1..{MAX_REPLICAS}")

    if action == "update_config":
        if args.get("key") not in ALLOWED_CONFIG_KEYS:
            return Decision("DENY", f"config key '{args.get('key')}' is not allowed")
        return Decision("NEEDS_APPROVAL", "configuration changes require human approval")

    if action == "restart_service" and service in PROTECTED_SERVICES:
        return Decision("NEEDS_APPROVAL", f"restarting protected service '{service}' requires approval")

    return Decision("ALLOW", "low-risk action within policy")