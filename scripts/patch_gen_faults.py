"""One-off patch: adds cache_stampede / external_outage faults and the cache_ttl_s policy key."""
from pathlib import Path


def patch(path: str, edits: list[tuple[str, str]]) -> None:
    p = Path(path)
    s = p.read_text()
    for old, new in edits:
        assert s.count(old) == 1, f"{path}: pattern not found exactly once: {old[:60]!r}"
        s = s.replace(old, new)
    p.write_text(s)
    print(f"patched {path}")


READ_ANCHOR = "    # ---------- agent-visible tools (read side) ----------\n"
NEW_METHODS = '''    def inject_cache_stampede(self):
        """Gateway cache TTL set far too low: every request misses and hammers the database."""
        gw = self.services["gateway"]
        gw.config["cache_ttl_s"] = 1
        self.deploys.append({"tick": self.tick, "service": "gateway", "version": gw.version,
                             "note": "config change: cache_ttl_s 300 -> 1"})
        self.faults.append({"type": "cache_stampede", "service": "gateway"})

    def inject_external_outage(self):
        """Third-party provider used by payments is down. No available action can fix it."""
        self.faults.append({"type": "external_outage", "service": "payments"})

'''

CFG_ANCHOR = '        self._log(service, "INFO", f"config {key} set to {value}")\n'
CFG_NEW = '''        if key == "cache_ttl_s":
            try:
                ok = int(value) >= 60
            except (TypeError, ValueError):
                ok = False
            if ok:
                self.faults = [f for f in self.faults if f["type"] != "cache_stampede"]
''' + CFG_ANCHOR

CASCADE_ANCHOR = "        # Cascade: callers inherit part of their dependencies' error rate\n"
CASCADE_NEW = '''        # Generalization faults (no effect, and no RNG use, unless injected)
        for f in self.faults:
            if f["type"] == "cache_stampede":
                t = target["database"]
                t["error_rate"] = 0.30 + self._noise(0.03)
                t["latency_ms"] = BASE_LATENCY["database"] * 6
                t["db_pool_used"] = self.services["database"].db_pool_max
                self._log("gateway", "WARN", "cache miss ratio 96%: every request falls through to the database")
                self._log("database", "ERROR", "too many concurrent queries: request queue saturated")
            elif f["type"] == "external_outage":
                t = target["payments"]
                t["error_rate"] = 0.40 + self._noise(0.03)
                t["latency_ms"] = BASE_LATENCY["payments"] * 3
                self._log("payments", "ERROR", "upstream provider PayCo returned 503 Service Unavailable")

''' + CASCADE_ANCHOR

patch("verifix/simulator.py", [
    (READ_ANCHOR, NEW_METHODS + READ_ANCHOR),
    (CFG_ANCHOR, CFG_NEW),
    (CASCADE_ANCHOR, CASCADE_NEW),
])
patch("verifix/policy.py", [
    ('ALLOWED_CONFIG_KEYS = {"max_connections", "timeout_ms"}',
     'ALLOWED_CONFIG_KEYS = {"max_connections", "timeout_ms", "cache_ttl_s"}'),
])