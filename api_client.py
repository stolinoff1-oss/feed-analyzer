import requests
import streamlit as st

SYSTEM_PROMPT = """Ты — опытный зоотехник-консультант по кормлению молочного скота.
Ты получаешь результаты лабораторного анализа кукурузного силоса и расчёт рациона.
Твоя задача — дать краткие, конкретные и практичные рекомендации:
1. Какой образец силоса лучше использовать для данного удоя и почему.
2. Какие риски (ацидоз, дефицит протеина, плесень и т.д.) и как их избежать.
3. Что скорректировать в рационе.
Отвечай структурированно, без воды, на русском языке."""

# === DeepSeek API (OpenAI-совместимый) ===
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_MODEL = "deepseek-chat"  # или "deepseek-reasoner" для более умной модели


def get_ai_recommendation(context: str) -> str:
    api_key = st.secrets.get("DEEPSEEK_API_KEY", "")
    if not api_key or not api_key.startswith("sk-"):
        return (
            "⚠️ API-ключ DeepSeek не задан в Secrets.\n\n"
            "Как исправить:\n"
            "1. Зайдите в Streamlit Cloud → Manage app → Settings → Secrets.\n"
            "2. Добавьте строку: DEEPSEEK_API_KEY = \"sk-ваш-ключ\"\n"
            "3. Сохраните — приложение перезапустится автоматически."
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": context},
        ],
        "temperature": 0.3,
        "stream": False,
    }
    try:
        r = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=120)
        if r.status_code == 401:
            return "❌ Ошибка 401: Неверный API-ключ DeepSeek. Проверьте ключ в Secrets."
        if r.status_code == 402:
            return "❌ Ошибка 402: Закончился баланс на DeepSeek. Пополните счёт на platform.deepseek.com."
        if r.status_code == 429:
            return "❌ Ошибка 429: Превышен лимит запросов. Подождите минуту и обновите."
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout:
        return "⏱️ Таймаут: DeepSeek не ответил за 2 минуты. Попробуйте ещё раз."
    except Exception as e:
        return f"❌ Ошибка API: {e}"
