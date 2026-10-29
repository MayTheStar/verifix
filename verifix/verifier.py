"""Deterministic verifier: judges recovery from real simulator metrics only.

It never reads the agent's claims. Verdict comes from numbers.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from verifix.simulator import SERVICES, Simulator

# Thresholds (SLO-like). Healthy baseline is ~0.005-0.007 error rate.
ERROR_RATE_OK = 0.05
LATENCY_FACTOR_OK = 2.0   # latency must be under 2x its baseline
BASE_LATENCY = {"gateway": 40, "auth": 30, "orders": 60, "payments": 80, "database": 15}


@dataclass
class Verdict:
    status: str                     # RECOVERED | PARTIAL | FAILED | DEGRADING
    healthy_services: list[str] = field(default_factory=list)
    unhealthy_services: list[str] = field(default_factory=list)
    window: int = 0
    details: dict = field(default_factory=dict)


def service_is_healthy(metrics: dict) -> bool:
    name = metrics["service"]
    return (
        metrics["error_rate"] < ERROR_RATE_OK
        and metrics["latency_ms"] < BASE_LATENCY[name] * LATENCY_FACTOR_OK
    )


def system_snapshot_healthy(sim: Simulator) -> tuple[list[str], list[str]]:
    healthy, unhealthy = [], []
    for name in SERVICES:
        (healthy if service_is_healthy(sim.query_metrics(name)) else unhealthy).append(name)
    return healthy, unhealthy


def verify_recovery(sim: Simulator, window: int = 8, stable_ticks: int = 4,
                    before_unhealthy: list[str] | None = None) -> Verdict:
    """Advance the simulation `window` ticks and judge from metric history.

    RECOVERED : all services healthy for the last `stable_ticks` ticks.
    DEGRADING : was healthy at some point in the window, then unhealthy again (flapping).
    PARTIAL   : strictly fewer unhealthy services than before the window, but not all healthy.
    FAILED    : no improvement.
    """
    # Capture the "before" state ourselves so callers cannot forget it.
    if before_unhealthy is None:
        _, before_unhealthy = system_snapshot_healthy(sim)

    start = len(sim.metric_history)
    sim.step(window)
    recent = sim.metric_history[start:]

    per_tick_ok = [all(service_is_healthy(snap[n]) for n in SERVICES) for snap in recent]
    healthy, unhealthy = system_snapshot_healthy(sim)

    if len(per_tick_ok) >= stable_ticks and all(per_tick_ok[-stable_ticks:]):
        status = "RECOVERED"
    elif any(per_tick_ok) and not per_tick_ok[-1]:
        status = "DEGRADING"
    elif unhealthy and len(unhealthy) < len(before_unhealthy):
        status = "PARTIAL"
    else:
        status = "FAILED"

    return Verdict(
        status=status,
        healthy_services=healthy,
        unhealthy_services=unhealthy,
        window=window,
        details={"per_tick_ok": per_tick_ok},
    )