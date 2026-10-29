from verifix.gen_scenarios import GenScenario, build_gen
from verifix.policy import evaluate_action
from verifix.verifier import verify_recovery


def make(fault):
    return build_gen(GenScenario(id="t", fault=fault, seed=200, expected="RECOVERED"))


def test_cache_stampede_hurts_database_and_cascades():
    sim = make("cache_stampede")
    assert sim.query_metrics("database")["error_rate"] > 0.2
    assert sim.query_metrics("gateway")["error_rate"] > 0.05


def test_raising_db_connections_does_not_fix_stampede():
    sim = make("cache_stampede")
    sim.update_config("database", "max_connections", 200)
    assert verify_recovery(sim, window=12).status != "RECOVERED"


def test_fixing_cache_ttl_recovers_stampede():
    sim = make("cache_stampede")
    sim.update_config("gateway", "cache_ttl_s", 300)
    assert verify_recovery(sim, window=14).status == "RECOVERED"


def test_external_outage_cannot_be_fixed_by_any_action():
    sim = make("external_outage")
    sim.restart_service("payments")
    sim.rollback_deploy("payments")
    sim.scale_service("payments", 5)
    assert verify_recovery(sim, window=14).status != "RECOVERED"


def test_bad_config_in_payments_needs_config_fix():
    sim = make("bad_config_payments")
    sim.rollback_deploy("payments")
    assert verify_recovery(sim, window=10).status != "RECOVERED"
    sim = make("bad_config_payments")
    sim.update_config("payments", "timeout_ms", 3000)
    assert verify_recovery(sim, window=14).status == "RECOVERED"


def test_cache_ttl_change_needs_approval():
    d = evaluate_action("update_config", {"service": "gateway", "key": "cache_ttl_s", "value": 300})
    assert d.verdict == "NEEDS_APPROVAL"