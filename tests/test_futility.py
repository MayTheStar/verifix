import itertools
import json

import verifix.agent as agent
from verifix.guards import SessionState, check_futility
from verifix.simulator import Simulator


def test_futility_triggers_after_four_failures():
    s = SessionState()
    for i in range(3):
        s.note_action("scale_service", {"service": "orders", "replicas": i + 2}, "FAILED")
    assert check_futility(s) is None
    s.note_action("restart_service", {"service": "orders"}, "FAILED")
    assert check_futility(s) is not None


def test_futility_does_not_trigger_if_some_progress():
    s = SessionState()
    for i, st in enumerate(["FAILED", "PARTIAL", "FAILED", "FAILED"]):
        s.note_action("scale_service", {"service": "orders", "replicas": i + 2}, st)
    assert check_futility(s) is None


def test_v2_is_off_in_v1():
    assert agent.V1.futility_guard is False and agent.V2.futility_guard is True