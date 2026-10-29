"""Non-LLM baselines. They use the same simulator tools and the same Policy Gate."""
from __future__ import annotations

from dataclasses import dataclass, field

from verifix.policy import evaluate_action
from verifix.simulator import SERVICES, Simulator
from verifix.verifier import verify_recovery


@dataclass
class BaselineResult:
    outcome: str
    final_status: str
    actions: list[dict] = field(default_factory=list)


def _worst_service(sim: Simulator) -> str:
    return max(SERVICES, key=lambda s: sim.query_metrics(s)["error_rate"])


def _try(sim: Simulator, action: str, args: dict, log: list[dict]) -> None:
    d = evaluate_action(action, args)
    entry = {"action": action, "args": args, "policy": d.verdict, "executed": False}
    if d.verdict == "ALLOW":          # baselines have no human: anything else is skipped
        if action == "restart_service":
            sim.restart_service(args["service"])
        elif action == "rollback_deploy":
            sim.rollback_deploy(args["service"])
        entry["executed"] = True
    log.append(entry)


def run_b0(sim: Simulator) -> BaselineResult:
    """B0: restart the service with the highest error rate."""
    log: list[dict] = []
    _try(sim, "restart_service", {"service": _worst_service(sim)}, log)
    final = verify_recovery(sim, window=20)
    return BaselineResult("RECOVERED" if final.status == "RECOVERED" else "FAILED",
                          final.status, log)


def run_b1(sim: Simulator) -> BaselineResult:
    """B1: rollback the worst service if it has a recent non-initial deploy, else restart it."""
    log: list[dict] = []
    worst = _worst_service(sim)
    recent = [d for d in sim.get_recent_deploys() if d["version"] != "v1.0.0" or "config" in d["note"]]
    if any(d["service"] == worst for d in recent):
        _try(sim, "rollback_deploy", {"service": worst}, log)
    else:
        _try(sim, "restart_service", {"service": worst}, log)
    final = verify_recovery(sim, window=20)
    return BaselineResult("RECOVERED" if final.status == "RECOVERED" else "FAILED",
                          final.status, log)