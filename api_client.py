import requests
import streamlit as st

SYSTEM_PROMPT = """Ты — опытный зоотехник-консультант по кормлению молочного скота.
Ты получаешь результаты лабораторного анализа кукурузного силоса и расчёт рациона.
Твоя задача — дать краткие, конкретные и практичные рекомендации:
1. Какой образец силоса лучше использовать для данного удоя и почему.
2. Какие риски (ацидоз, дефицит протеина, плесень и т.д.) и как их избежать.
3. Что скорректировать в рационе.
Отвечай структурированно, без воды, на русском языке."""

# === AIAI.BY (OpenAI-совместимый) ===
AIAI_API_URL = "https://api.aiai.by/v1/chat/completions"
AIAI_MODEL = "deepseek-chat"


def get_ai_recommendation(context: str) -> str:
    # Ключ читаем из Secrets (безопасно). В коде его больше нет.
    api_key = st.secrets.get("AIAI_API_KEY", "")
    if not api_key or not api_key.startswith("sk-"):
        return (
            "⚠️ API-ключ AIAI.BY не задан в Secrets.\n\n"
            "Откройте Manage app → ⋮ → Settings → Secrets и добавьте строку:\n"
            'AIAI_API_KEY = "sk-vedai-ваш-ключ"'
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": AIAI_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": context},
        ],
        "temperature": 0.3,
    }
    try:
        r = requests.post(AIAI_API_URL, headers=headers, json=payload, timeout=120)
        if r.status_code == 401:
            return "❌ Ошибка 401: Неверный ключ AIAI.BY. Проверьте Secrets."
        if r.status_code == 402:
            return "❌ Ошибка 402: Закончился баланс AIAI.BY."
        if r.status_code == 429:
            return "❌ Ошибка 429: Превышен лимит запросов."
        if r.status_code >= 400:
            return f"❌ Ошибка {r.status_code}: {r.text[:500]}"
        return r.json()["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout:
        return "⏱️ Таймаут: сервер не ответил за 2 минуты."
    except Exception as e:
        return f"❌ Ошибка: {e}"
