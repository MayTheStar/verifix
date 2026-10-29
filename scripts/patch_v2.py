"""One-off patch: adds the futility guard and the v2 config."""
from pathlib import Path


def patch(path, edits):
    p = Path(path)
    s = p.read_text()
    for old, new in edits:
        assert s.count(old) == 1, f"{path}: pattern not found exactly once: {old[:60]!r}"
        s = s.replace(old, new)
    p.write_text(s)
    print(f"patched {path}")


patch("verifix/guards.py", [
    (
        "def check_repeat(",
        '''FUTILITY_LIMIT = 4


def check_futility(state: SessionState, limit: int = FUTILITY_LIMIT) -> str | None:
    """Stop flailing: after `limit` executed actions with no improvement, force escalation."""
    statuses = list(state.tried.values())
    if len(statuses) >= limit and not any(s in ("PARTIAL", "RECOVERED") for s in statuses):
        return (f"{len(statuses)} executed actions produced no measurable improvement. "
                "Further actions are blocked. The root cause is probably outside what you can "
                "fix with the available actions. Call finish with escalate=true and explain your findings.")
    return None


def check_repeat(''',
    ),
])

patch("verifix/agent.py", [
    ("from verifix.guards import HINTS, SessionState, check_investigation, check_repeat",
     "from verifix.guards import HINTS, SessionState, check_futility, check_investigation, check_repeat"),
    ("    budget_warning: bool = False\n",
     "    budget_warning: bool = False\n    futility_guard: bool = False\n"),
    ('CONFIGS = {\n',
     'V2 = replace(V1, name="v2", futility_guard=True)\nCONFIGS = {\n    "v2": V2,\n'),
    ("    if blocked is None and config.repeat_guard:\n",
     "    if blocked is None and config.futility_guard:\n"
     "        blocked = check_futility(state)\n"
     "    if blocked is None and config.repeat_guard:\n"),
])