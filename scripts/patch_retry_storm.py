"""One-off patch: adds the retry_storm option to the simulator. Run once."""
from pathlib import Path

p = Path("verifix/simulator.py")
s = p.read_text()

edits = [
    (
        "def __init__(self, seed: int = 0, red_herrings: bool = False):\n"
        "        self.rng = random.Random(seed)\n"
        "        self.red_herrings = red_herrings\n",
        "def __init__(self, seed: int = 0, red_herrings: bool = False, retry_storm: bool = False):\n"
        "        self.rng = random.Random(seed)\n"
        "        self.red_herrings = red_herrings\n"
        "        self.retry_storm = retry_storm\n",
    ),
    (
        '                inherited = target[callee]["error_rate"] * 0.6\n',
        '                inherited = target[callee]["error_rate"] * 0.6\n'
        '                if self.retry_storm and caller == "orders":\n'
        "                    inherited = min(0.9, inherited * 2.2)  # retries amplify errors in orders\n",
    ),
]

for old, new in edits:
    assert s.count(old) == 1, f"pattern not found exactly once: {old[:50]!r}"
    s = s.replace(old, new)

p.write_text(s)
print("patched OK")