import requests
import streamlit as st

SYSTEM_PROMPT = """Ты — опытный зоотехник-консультант по кормлению молочного скота.
Ты получаешь результаты лабораторного анализа кукурузного силоса и расчёт рациона.
Твоя задача — дать краткие, конкретные и практичные рекомендации:
1. Какой образец силоса лучше использовать для данного удоя и почему.
2. Какие риски (ацидоз, дефицит протеина, плесень и т.д.) и как их избежать.
3. Что скорректировать в рационе.
Отвечай структурированно, без воды, на русском языке."""

# === AIAI.BY / Vedai (OpenAI-совместимый) ===
AIAI_API_URL = "https://api.bycom.by/v1/chat/completions"
AIAI_MODEL = "aion-2.0"  # из документации; при желании замените на другую доступную


def get_ai_recommendation(context: str) -> str:
    api_key = st.secrets.get("AIAI_API_KEY", "")
    if not api_key or not api_key.startswith("sk-"):
        return (
            "⚠️ API-ключ AIAI.BY не задан в Secrets.\n\n"
            "Как исправить:\n"
            "1. Зайдите в Streamlit Cloud → Manage app → Settings → Secrets.\n"
            "2. Добавьте строку: AIAI_API_KEY = \"sk-vedai-ваш-ключ\"\n"
            "3. Сохраните — приложение перезапустится автоматически."
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
            return "❌ Ошибка 401: Неверный API-ключ AIAI.BY. Проверьте ключ в Secrets."
        if r.status_code == 402:
            return "❌ Ошибка 402: Закончился баланс на AIAI.BY. Пополните счёт на console.aiai.by."
        if r.status_code == 429:
            return "❌ Ошибка 429: Превышен лимит запросов. Подождите минуту и обновите."
        if r.status_code >= 400:
            return f"❌ Ошибка {r.status_code}: {r.text[:500]}"
        return r.json()["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout:
        return "⏱️ Таймаут: AIAI.BY не ответил за 2 минуты. Попробуйте ещё раз."
    except Exception as e:
        return f"❌ Ошибка API: {e}"
