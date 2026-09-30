import requests
import streamlit as st

SYSTEM_PROMPT = """Ты — опытный зоотехник-консультант по кормлению молочного скота.
Ты получаешь результаты лабораторного анализа кукурузного силоса и расчёт рациона.
Твоя задача — дать краткие, конкретные и практичные рекомендации:
1. Какой образец силоса лучше использовать для данного удоя и почему.
2. Какие риски (ацидоз, дефицит протеина, плесень и т.д.) и как их избежать.
3. Что скорректировать в рационе.
Отвечай структурированно, без воды, на русском языке."""

def get_ai_recommendation(context: str) -> str:
    api_key = st.secrets.get("OPENAI_API_KEY", "")
    if not api_key or api_key == "sk-...":
        return "[API-ключ не задан в Secrets — рекомендации пропущены. Добавьте OPENAI_API_KEY в настройках Streamlit Cloud.]"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": "gpt-4o-mini", "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": context}], "temperature": 0.3}
    try:
        r = requests.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[Ошибка API: {e}]"
