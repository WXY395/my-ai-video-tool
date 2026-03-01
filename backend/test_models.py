import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

print("可用的 Gemini 模型：")
print("=" * 50)

for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(f"✅ {m.name}")

print("=" * 50)