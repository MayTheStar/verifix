from verifix.simulator import Simulator


def test_healthy_system_stays_healthy():
    sim = Simulator(seed=1)
    sim.step(10)
    for name in sim.services:
        assert sim.query_metrics(name)["error_rate"] < 0.05


def test_bad_deploy_causes_errors_and_cascade():
    sim = Simulator(seed=1)
    sim.step(3)
    sim.inject_bad_deploy("payments")
    sim.step(6)
    assert sim.query_metrics("payments")["error_rate"] > 0.2
    assert sim.query_metrics("orders")["error_rate"] > 0.05  # cascade


def test_rollback_recovers_system():
    sim = Simulator(seed=1)
    sim.step(3)
    sim.inject_bad_deploy("payments")
    sim.step(5)
    sim.rollback_deploy("payments")
    sim.step(10)
    assert sim.query_metrics("payments")["error_rate"] < 0.05


def test_restart_does_not_fix_bad_deploy():
    sim = Simulator(seed=1)
    sim.step(3)
    sim.inject_bad_deploy("payments")
    sim.step(4)
    sim.restart_service("payments")
    sim.step(8)
    assert sim.query_metrics("payments")["error_rate"] > 0.2


def test_db_pool_exhaustion_and_config_fix():
    sim = Simulator(seed=2)
    sim.step(3)
    sim.inject_db_pool_exhaustion()
    sim.step(6)
    assert sim.query_metrics("database")["error_rate"] > 0.2
    sim.update_config("database", "max_connections", 200)
    sim.step(10)
    assert sim.query_metrics("database")["error_rate"] < 0.05


def test_same_seed_is_reproducible():
    a, b = Simulator(seed=7), Simulator(seed=7)
    for sim in (a, b):
        sim.step(2)
        sim.inject_bad_deploy("auth")
        sim.step(5)
    assert a.query_metrics("auth") == b.query_metrics("auth")