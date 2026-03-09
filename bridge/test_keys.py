"""
V35.0 API Key Connectivity Test
Run: python bridge/test_keys.py
"""

import os
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

PASS = "[PASS]"
FAIL = "[FAIL]"
results = {}

# ── 1. Google Gemini ───────────────────────────────────────────────────────────
print("\n[1/3] Testing Google Gemini (gemini-2.5-flash)...")
try:
    from google import genai
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    resp = client.models.generate_content(
        model="gemini-2.5-flash",
        contents="Reply with exactly one word: Hello",
    )
    text = resp.text.strip()
    print(f"  Response: {text!r}")
    results["Gemini"] = (PASS, text)
except Exception as e:
    results["Gemini"] = (FAIL, str(e))
    print(f"  Error: {e}")

# ── 2. OpenAI GPT-4o-mini ──────────────────────────────────────────────────────
print("\n[2/3] Testing OpenAI (gpt-4o-mini)...")
try:
    from openai import OpenAI
    oa = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    resp = oa.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Reply with exactly one word: Hello"}],
        max_tokens=10,
    )
    text = resp.choices[0].message.content.strip()
    print(f"  Response: {text!r}")
    results["OpenAI"] = (PASS, text)
except Exception as e:
    results["OpenAI"] = (FAIL, str(e))
    print(f"  Error: {e}")

# ── 3. Replicate flux-schnell ──────────────────────────────────────────────────
print("\n[3/3] Testing Replicate (black-forest-labs/flux-schnell)...")
try:
    import replicate
    client_r = replicate.Client(api_token=os.environ["REPLICATE_API_TOKEN"])
    # metadata-only call — no image generated, no cost
    model = client_r.models.get("black-forest-labs/flux-schnell")
    print(f"  Model found: {model.name} — {model.description[:60] if model.description else 'no description'}")
    results["Replicate"] = (PASS, model.name)
except Exception as e:
    results["Replicate"] = (FAIL, str(e))
    print(f"  Error: {e}")

# ── Report ─────────────────────────────────────────────────────────────────────
print("\n" + "═" * 50)
print("  V35.0 API KEY STATUS REPORT")
print("═" * 50)
all_ok = True
for name, (status, detail) in results.items():
    print(f"  {status}  {name:12s}  {detail[:60]}")
    if status == FAIL:
        all_ok = False
print("═" * 50)
if all_ok:
    print("  ALL GREEN — ready to build bridge/main.py")
else:
    print("  FIX failing keys before proceeding")
print()
