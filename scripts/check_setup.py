"""Milestone 1: verify the environment, API key, and one tiny model call."""
import os
import sys

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
if not api_key or api_key.endswith("your-key-here"):
    sys.exit("ERROR: OPENAI_API_KEY is missing in .env")

model = os.getenv("VERIFIX_MODEL", "gpt-4o-mini")
client = OpenAI(api_key=api_key)

print(f"Python OK: {sys.version.split()[0]}")

# 1) List models available to this account (names only, filtered for small/cheap ones)
try:
    names = sorted(m.id for m in client.models.list().data)
    small = [n for n in names if any(tag in n for tag in ("mini", "nano"))]
    print(f"Total models visible: {len(names)}")
    print("Small/cheap candidates:")
    for n in small:
        print("  -", n)
except Exception as e:
    print(f"WARNING: could not list models: {e}")

# 2) One tiny call to prove the key works
print(f"\nTesting a tiny call with model: {model}")
try:
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": "Reply with exactly: ready"}],
        max_completion_tokens=20,
    )
    print("Model replied:", resp.choices[0].message.content)
    u = resp.usage
    print(f"Tokens -> prompt: {u.prompt_tokens}, completion: {u.completion_tokens}")
    print("SETUP OK")
except Exception as e:
    print(f"ERROR during model call: {e}")