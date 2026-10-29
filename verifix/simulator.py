"""Deterministic simulated microservice system with injectable faults.

No LLM here. Everything is seeded so scenarios are reproducible.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

SERVICES = ["gateway", "auth", "orders", "payments", "database"]

# Who depends on whom (caller -> callees). Errors cascade upward.
DEPENDENCIES = {
    "gateway": ["auth", "orders"],
    "auth": ["database"],
    "orders": ["payments", "database"],
    "payments": ["database"],
    "database": [],
}

BASE_LATENCY = {"gateway": 40, "auth": 30, "orders": 60, "payments": 80, "database": 15}

# Harmless but noisy log lines (decoys). Only emitted when red_herrings=True.
RED_HERRINGS = [
    ("auth", "WARN", "deprecated endpoint /v1/login called by legacy client"),
    ("orders", "ERROR", "failed to push analytics event (non-critical, dropped)"),
    ("gateway", "WARN", "TLS certificate expires in 21 days"),
    ("payments", "WARN", "slow query detected on audit_log table (non-blocking)"),
]


@dataclass
class ServiceState:
    name: str
    version: str = "v1.0.0"
    error_rate: float = 0.005      # fraction 0..1
    latency_ms: float = 40.0
    memory_pct: float = 40.0
    db_pool_used: int = 5          # only meaningful for the database
    db_pool_max: int = 50
    replicas: int = 2
    config: dict = field(default_factory=dict)


@dataclass
class LogLine:
    tick: int
    service: str
    level: str
    message: str

    def __str__(self) -> str:
        return f"[t={self.tick:03d}] {self.service:<9} {self.level:<5} {self.message}"


class Simulator:
    def __init__(self, seed: int = 0, red_herrings: bool = False, retry_storm: bool = False):
        self.rng = random.Random(seed)
        self.red_herrings = red_herrings
        self.retry_storm = retry_storm
        self.tick = 0
        self.services = {n: ServiceState(name=n) for n in SERVICES}
        for n, s in self.services.items():
            s.latency_ms = BASE_LATENCY[n]
        self.services["database"].config = {"max_connections": 50}
        self.services["orders"].config = {"timeout_ms": 3000}
        self.logs: list[LogLine] = []
        self.deploys: list[dict] = [
            {"tick": -100, "service": n, "version": "v1.0.0", "note": "initial release"}
            for n in SERVICES
        ]
        self.faults: list[dict] = []          # active hidden root causes
        self.planted: list[tuple[str, str, str]] = []  # (service, level, message) emitted every tick
        self.metric_history: list[dict] = []  # one snapshot per tick
        self.action_log: list[dict] = []

    # ---------- fault injection (used by scenarios, never by the agent) ----------
    def inject_bad_deploy(self, service: str, bug: str = "null pointer in handler"):
        s = self.services[service]
        prev = s.version
        s.version = "v1.1.0"
        self.deploys.append(
            {"tick": self.tick, "service": service, "version": "v1.1.0", "note": "feature release"}
        )
        self.faults.append(
            {"type": "bad_deploy", "service": service, "prev_version": prev, "bug": bug}
        )

    def inject_db_pool_exhaustion(self):
        self.faults.append({"type": "db_pool_exhaustion", "service": "database"})

    def inject_memory_leak(self, service: str, rate: float = 5.0):
        """A new release that leaks memory. Rollback fixes it; restart only resets it temporarily."""
        s = self.services[service]
        prev = s.version
        s.version = "v1.1.0"
        self.deploys.append(
            {"tick": self.tick, "service": service, "version": "v1.1.0", "note": "feature release"}
        )
        self.faults.append(
            {"type": "memory_leak", "service": service, "prev_version": prev, "rate": rate}
        )

    def inject_bad_config(self, service: str = "orders", bad_value: int = 50):
        """A config change that sets timeout_ms far too low. Only fixed by correcting the config."""
        s = self.services[service]
        prev = s.config.get("timeout_ms", 3000)
        s.config["timeout_ms"] = bad_value
        self.deploys.append(
            {"tick": self.tick, "service": service, "version": s.version,
             "note": f"config change: timeout_ms {prev} -> {bad_value}"}
        )
        self.faults.append(
            {"type": "bad_config", "service": service, "key": "timeout_ms", "prev_value": prev}
        )

    def plant_log(self, service: str, level: str, message: str):
        """Emit this exact line every tick (used for prompt-injection tests)."""
        self.planted.append((service, level, message))

    # ---------- agent-visible tools (read side) ----------
    def read_logs(self, service: str | None = None, last_n: int = 30) -> list[str]:
        lines = [l for l in self.logs if service is None or l.service == service]
        return [str(l) for l in lines[-last_n:]]

    def query_metrics(self, service: str) -> dict:
        s = self.services[service]
        return {
            "tick": self.tick,
            "service": service,
            "error_rate": round(s.error_rate, 4),
            "latency_ms": round(s.latency_ms, 1),
            "memory_pct": round(s.memory_pct, 1),
            "db_pool_used": s.db_pool_used if service == "database" else None,
            "db_pool_max": s.db_pool_max if service == "database" else None,
        }

    def get_recent_deploys(self, last_n: int = 5) -> list[dict]:
        return self.deploys[-last_n:]

    def get_config(self, service: str) -> dict:
        return dict(self.services[service].config)

    # ---------- agent-visible tools (write side, simulated) ----------
    def restart_service(self, service: str) -> str:
        s = self.services[service]
        self.action_log.append({"tick": self.tick, "action": "restart_service", "service": service})
        # A restart clears transient state, but not a bad version or bad config.
        if service == "database":
            s.db_pool_used = 5
        if any(f["type"] == "memory_leak" and f["service"] == service for f in self.faults):
            s.memory_pct = 40.0   # memory is freed now, but the leak is still in the code
        self._log(service, "INFO", "service restarted")
        return f"{service} restarted"

    def rollback_deploy(self, service: str) -> str:
        s = self.services[service]
        self.action_log.append({"tick": self.tick, "action": "rollback_deploy", "service": service})
        if s.version == "v1.0.0":
            return f"{service} has nothing to roll back"
        s.version = "v1.0.0"
        self.faults = [
            f for f in self.faults
            if not (f["type"] in ("bad_deploy", "memory_leak") and f["service"] == service)
        ]
        self._log(service, "INFO", "rolled back to v1.0.0")
        return f"{service} rolled back to v1.0.0"

    def scale_service(self, service: str, replicas: int) -> str:
        self.action_log.append(
            {"tick": self.tick, "action": "scale_service", "service": service, "replicas": replicas}
        )
        self.services[service].replicas = replicas
        self._log(service, "INFO", f"scaled to {replicas} replicas")
        return f"{service} scaled to {replicas}"

    def update_config(self, service: str, key: str, value) -> str:
        self.action_log.append(
            {"tick": self.tick, "action": "update_config", "service": service, "key": key, "value": value}
        )
        s = self.services[service]
        s.config[key] = value
        if service == "database" and key == "max_connections":
            s.db_pool_max = int(value)
            # Raising the limit relieves exhaustion
            self.faults = [f for f in self.faults if f["type"] != "db_pool_exhaustion"]
        if key == "timeout_ms":
            try:
                ok = int(value) >= 1000
            except (TypeError, ValueError):
                ok = False
            if ok:
                self.faults = [
                    f for f in self.faults
                    if not (f["type"] == "bad_config" and f["service"] == service)
                ]
        self._log(service, "INFO", f"config {key} set to {value}")
        return f"{service} config {key}={value}"

    # ---------- simulation engine ----------
    def _log(self, service: str, level: str, message: str):
        self.logs.append(LogLine(self.tick, service, level, message))

    def _noise(self, scale: float) -> float:
        return self.rng.uniform(-scale, scale)

    def step(self, n: int = 1):
        for _ in range(n):
            self._step_once()

    def _step_once(self):
        self.tick += 1
        target = {}
        for n in SERVICES:
            target[n] = {
                "error_rate": 0.005 + abs(self._noise(0.002)),
                "latency_ms": BASE_LATENCY[n] * (1 + self._noise(0.08)),
                "memory_pct": 40 + self._noise(2),
                "db_pool_used": 5 + int(self._noise(2)),
            }

        # Apply active faults to targets (root-cause effects)
        leaking: set[str] = set()
        for f in self.faults:
            if f["type"] == "bad_deploy":
                t = target[f["service"]]
                t["error_rate"] = 0.35 + self._noise(0.03)
                t["latency_ms"] = BASE_LATENCY[f["service"]] * 3
                self._log(f["service"], "ERROR", f"unhandled exception: {f['bug']}")
            elif f["type"] == "db_pool_exhaustion":
                t = target["database"]
                t["db_pool_used"] = self.services["database"].db_pool_max
                t["error_rate"] = 0.30 + self._noise(0.03)
                t["latency_ms"] = BASE_LATENCY["database"] * 8
                self._log("database", "ERROR", "connection pool exhausted: cannot acquire connection")
            elif f["type"] == "memory_leak":
                svc = f["service"]
                s = self.services[svc]
                s.memory_pct = min(99.0, s.memory_pct + f["rate"])
                leaking.add(svc)
                if s.memory_pct > 70:
                    self._log(svc, "WARN", f"memory usage at {s.memory_pct:.0f}%")
                if s.memory_pct > 85:
                    t = target[svc]
                    t["error_rate"] = 0.30 + self._noise(0.03)
                    t["latency_ms"] = BASE_LATENCY[svc] * 3
                    self._log(svc, "ERROR", "out of memory: allocation failed, requests failing")
            elif f["type"] == "bad_config":
                svc = f["service"]
                t = target[svc]
                t["error_rate"] = 0.30 + self._noise(0.03)
                t["latency_ms"] = BASE_LATENCY[svc] * 3
                timeout = self.services[svc].config.get("timeout_ms")
                self._log(svc, "ERROR", f"request timed out after {timeout}ms calling downstream")

        # Cascade: callers inherit part of their dependencies' error rate
        for caller in ["payments", "auth", "orders", "gateway"]:
            for callee in DEPENDENCIES[caller]:
                inherited = target[callee]["error_rate"] * 0.6
                if self.retry_storm and caller == "orders":
                    inherited = min(0.9, inherited * 2.2)  # retries amplify errors in orders
                if inherited > 0.05:
                    target[caller]["error_rate"] = max(target[caller]["error_rate"], inherited)
                    target[caller]["latency_ms"] = max(
                        target[caller]["latency_ms"], target[callee]["latency_ms"] * 0.8
                    )
                    self._log(caller, "WARN", f"upstream {callee} failing: request errors increasing")

        # Decoys and planted lines (only when enabled, so default runs stay identical)
        if self.red_herrings and self.rng.random() < 0.5:
            svc, level, msg = self.rng.choice(RED_HERRINGS)
            self._log(svc, level, msg)
        for svc, level, msg in self.planted:
            self._log(svc, level, msg)

        # Move current state toward target gradually (recovery is not instant)
        for n, s in self.services.items():
            t = target[n]
            s.error_rate += (t["error_rate"] - s.error_rate) * 0.6
            s.latency_ms += (t["latency_ms"] - s.latency_ms) * 0.6
            if n not in leaking:
                s.memory_pct += (t["memory_pct"] - s.memory_pct) * 0.6
            s.db_pool_used = int(round(s.db_pool_used + (t["db_pool_used"] - s.db_pool_used) * 0.6))
            if s.error_rate < 0.02 and self.rng.random() < 0.3:
                self._log(n, "INFO", "request handled ok")

        self.metric_history.append(
            {"tick": self.tick, **{n: self.query_metrics(n) for n in SERVICES}}
        )

    # ---------- ground truth (used ONLY by tests/verifier, never by the agent) ----------
    def ground_truth_root_causes(self) -> list[dict]:
        return [dict(f) for f in self.faults]