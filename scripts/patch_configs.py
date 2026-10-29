"""One-off patch: adds two ablation configs to verifix/agent.py. Run once."""
from pathlib import Path

p = Path("verifix/agent.py")
s = p.read_text()

old = '    "v1-no-warning": replace(V1, name="v1-no-warning", budget_warning=False),\n}'
new = (
    '    "v1-no-warning": replace(V1, name="v1-no-warning", budget_warning=False),\n'
    '    "v0-20steps": replace(V0, name="v0-20steps", max_steps=20),\n'
    '    "gate-only": replace(V0, name="gate-only", max_steps=20, investigation_gate=True),\n'
    '}'
)
assert s.count(old) == 1, "pattern not found exactly once"
p.write_text(s.replace(old, new))
print("patched OK")