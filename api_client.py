import requests

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

# ⚠️ ВНИМАНИЕ: ключ вписан прямо в код. Не публикуйте этот файл.
# Как только всё заработает — перенесите ключ обратно в Secrets и удалите отсюда.
AIAI_API_KEY = "sk-vedai-Zqym3Wk0VsES1RsAPsrNYLpuSR7H1ovPErAV8gTyiBU"


def get_ai_recommendation(context: str) -> str:
    if not AIAI_API_KEY or not AIAI_API_KEY.startswith("sk-"):
        return "⚠️ API-ключ не задан в коде."

    headers = {
        "Authorization": f"Bearer {AIAI_API_KEY}",
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
            return f"❌ Ошибка 401: Неверный ключ.\nURL: {AIAI_API_URL}\nМодель: {AIAI_MODEL}\nОтвет сервера: {r.text[:400]}"
        if r.status_code == 402:
            return "❌ Ошибка 402: Закончился баланс AIAI.BY."
        if r.status_code == 429:
            return "❌ Ошибка 429: Слишком много запросов."
        if r.status_code >= 400:
            return f"❌ Ошибка {r.status_code}: {r.text[:500]}"
        return r.json()["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout:
        return "⏱️ Таймаут: сервер не ответил за 2 минуты."
    except Exception as e:
        return f"❌ Ошибка: {e}"
