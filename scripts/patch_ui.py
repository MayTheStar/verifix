"""One-off UI polish: gradient hero and softer metric cards."""
from pathlib import Path

p = Path("app/dashboard.py")
s = p.read_text()
anchor = "</style>"
assert s.count(anchor) == 1, "style anchor not found exactly once"
extra = """
.vx-hero {padding: 18px 22px; border-radius: 14px; margin-bottom: 14px;
  background: linear-gradient(135deg, rgba(79,140,255,.22), rgba(163,113,247,.14));
  border: 1px solid rgba(79,140,255,.35);}
[data-testid="stMetric"] {background: rgba(128,128,128,.08); padding: 12px 14px;
  border-radius: 12px; border: 1px solid rgba(128,128,128,.25);}
.vx-stage {transition: transform .15s ease;}
.vx-stage:hover {transform: translateY(-2px);}
"""
p.write_text(s.replace(anchor, extra + anchor))
print("patched OK")