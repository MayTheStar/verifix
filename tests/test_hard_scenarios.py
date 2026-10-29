from verifix.baselines import run_b1
from verifix.scenarios import Scenario, build
from verifix.verifier import verify_recovery


def trap():
    return build(Scenario(id="t", fault="cascade_trap", service="payments", seed=100))


def dual():
    return build(Scenario(id="d", fault="dual_fault", service="auth", seed=100))


def test_cascade_trap_victim_is_louder_than_root_cause():
    sim = trap()
    assert sim.query_metrics("orders")["error_rate"] > sim.query_metrics("payments")["error_rate"]


def test_cascade_trap_fools_b1():
    r = run_b1(trap())
    assert r.outcome != "RECOVERED"


def test_cascade_trap_fixed_by_rolling_back_the_real_root_cause():
    sim = trap()
    sim.rollback_deploy("payments")
    assert verify_recovery(sim, window=14).status == "RECOVERED"


def test_dual_fault_needs_both_fixes():
    sim = dual()
    sim.rollback_deploy("auth")
    assert verify_recovery(sim, window=12).status != "RECOVERED"

    sim = dual()
    sim.rollback_deploy("auth")
    sim.update_config("orders", "timeout_ms", 3000)
    assert verify_recovery(sim, window=14).status == "RECOVERED"


def test_dual_fault_fools_b1():
    assert run_b1(dual()).outcome != "RECOVERED"