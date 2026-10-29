import itertools
import json

import verifix.agent as agent
from verifix.guards import SessionState, check_investigation, check_repeat
from verifix.simulator import Simulator


def broken_payments():
    sim = Simulator(seed=1)
    sim.step(3)
    sim.inject_bad_deploy("payments")
    sim.step(5)
    return sim


def fake_llm(monkeypatch, script):
    it = iter(script)
    counter = itertools.count()

    def fake_chat(messages, tools=None, model=None, temperature=0.0):
        name, args = next(it)
        return {"content": "", "tool_calls": [{"id": f"c{next(counter)}", "name": name,
                                                "arguments": json.dumps(args)}],
                "prompt_tokens": 0, "completion_tokens": 0, "cached": True}

    monkeypatch.setattr(agent, "chat", fake_chat)


def actions(result):
    return [t for t in result.trace if t["type"] == "action"]


def propose(action, service, **extra):
    return ("propose_action", {"action": action, "service": service, "evidence": [],
                               "rationale": "r", "confidence": 0.5, **extra})


# ---------- pure guard logic ----------
def test_gate_requires_deploys_and_config():
    s = SessionState()
    assert check_investigation(s, "orders") is not None
    s.note_read("get_recent_deploys", {})
    assert check_investigation(s, "orders") is not None
    s.note_read("get_config", {"service": "orders"})
    assert check_investigation(s, "orders") is None


def test_repeat_guard_blocks_scale_with_different_replicas():
    s = SessionState()
    s.note_action("scale_service", {"service": "database", "replicas": 2}, "FAILED")
    assert check_repeat(s, "scale_service", {"service": "database", "replicas": 3}) is not None


def test_repeat_guard_allows_config_retry_with_new_value():
    s = SessionState()
    s.note_action("update_config", {"service": "orders", "key": "timeout_ms", "value": 100}, "FAILED")
    assert check_repeat(s, "update_config",
                        {"service": "orders", "key": "timeout_ms", "value": 3000}) is None


# ---------- inside the agent loop (fake LLM, free) ----------
def test_gate_blocks_action_before_investigation(monkeypatch):
    fake_llm(monkeypatch, [
        propose("restart_service", "payments"),
        ("get_recent_deploys", {}),
        ("get_config", {"service": "payments"}),
        propose("rollback_deploy", "payments"),
        ("finish", {"summary": "ok", "claims_recovered": True, "escalate": False}),
    ])
    result = agent.run_incident(broken_payments(), config=agent.V1)
    acts = actions(result)
    assert acts[0]["policy"] == "BLOCKED" and acts[0]["executed"] is False
    assert acts[1]["executed"] is True
    assert result.outcome == "RECOVERED"


def test_repeat_guard_blocks_second_identical_failed_action(monkeypatch):
    fake_llm(monkeypatch, [
        ("get_recent_deploys", {}),
        ("get_config", {"service": "payments"}),
        propose("restart_service", "payments"),
        propose("restart_service", "payments"),
        ("finish", {"summary": "need a human", "claims_recovered": False, "escalate": True}),
    ])
    result = agent.run_incident(broken_payments(), config=agent.V1)
    acts = actions(result)
    assert acts[0]["executed"] is True and acts[0]["verdict"] != "RECOVERED"
    assert acts[1]["policy"] == "BLOCKED" and acts[1]["executed"] is False
    assert result.outcome == "ESCALATED"


def test_running_out_of_steps_is_timed_out(monkeypatch):
    fake_llm(monkeypatch, [("query_metrics", {"service": "payments"})] * 2)
    result = agent.run_incident(broken_payments(), max_steps=2)
    assert result.finish is None
    assert result.outcome == "TIMED_OUT"