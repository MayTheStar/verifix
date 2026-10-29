"""Fix: futility guard must count executed actions, not distinct signatures."""
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
        "    tried: dict = field(default_factory=dict)   # signature -> verifier status\n",
        "    tried: dict = field(default_factory=dict)   # signature -> verifier status\n"
        "    history: list = field(default_factory=list)  # every executed action's verifier status, in order\n",
    ),
    (
        "        self.tried[signature(action, args)] = status\n",
        "        self.tried[signature(action, args)] = status\n"
        "        self.history.append(status)\n",
    ),
    (
        "    statuses = list(state.tried.values())\n",
        "    statuses = state.history\n",
    ),
])