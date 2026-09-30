import requests
import streamlit as st
import hashlib


SYSTEM_PROMPT = """Ты — опытный зоотехник-консультант по кормлению молочного скота.
Ты получаешь результаты лабораторного анализа кукурузного силоса, расчёт рациона
и параметры конкретной коровы. Твоя задача — дать краткие, конкретные и практичные
рекомендации:
1. Какой образец силоса лучше использовать для данной коровы и почему.
2. Какие риски (ацидоз, дефицит протеина, плесень, низкая поедаемость и т.д.)
   и как их избежать.
3. Что скорректировать в рационе (буферы, патока, жир, шрот, премиксы) —
   с конкретными дозировками в граммах/кг на голову в сутки.
4. Что исключить или ограничить.
Отвечай структурированно, без воды, на русском языке. Учитывай удой и живую массу."""


AIAI_API_URL = "https://api.aiai.by/v1/chat/completions"
AIAI_MODEL = "deepseek-chat"


def _make_cache_key(context: str) -> str:
    return hashlib.sha256(context.encode("utf-8")).hexdigest()


@st.cache_data(ttl=3600, show_spinner=False)
def _call_api(context_hash: str, context: str) -> str:
    """Реальный запрос к AIAI.BY. Кэшируется по хэшу контекста."""
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


def build_context(analysis: dict, rations: dict,
                  live_weight: float, milk_yield: float) -> str:
    """Формирует расширенный контекст для AI."""
    lines = [
        "=== ПАРАМЕТРЫ КОРОВЫ ===",
        f"Живая масса: {live_weight} кг",
        f"Суточный удой: {milk_yield} кг",
        "",
        "=== РЕЗУЛЬТАТЫ АНАЛИЗА СИЛОСА ===",
        "Формат: имя | DM г/кг | СП | крахмал | сахар | НДК | КДК | "
        "перев. ОВ % | NEL-VC | RNB | структурный | балл",
    ]
    for s in analysis["ratings"]:
        lines.append(
            f"{s['name']} | "
            f"DM={s.get('DM')} | СП={s.get('CP')} | крахмал={s.get('starch')} | "
            f"сахар={s.get('sugar')} | НДК={s.get('NDF')} | КДК={s.get('ADF')} | "
            f"перев.ОВ={s.get('dOM')}% | NEL-VC={s.get('NEL_VC')} | "
            f"RNB={s.get('RNB')} | структ={s.get('structure')} | "
            f"балл={s.get('score')}"
        )

    lines.append("")
    lines.append("=== РАСЧЁТ РАЦИОНОВ (топ-2 образца) ===")
    for name, r in rations.items():
        n = r["norms"]
        t = r["total"]
        lines.append(
            f"\n--- Рацион на основе: {name} ---\n"
            f"Норма: NEL={n['NEL']} МДж, nXP={n['nXP']} г, СВ={n['DM']} кг\n"
            f"Итого: NEL={t['NEL']:.1f} МДж, nXP={t['nXP']:.0f} г, СВ={t['dm']:.2f} кг\n"
            f"НДК в рационе: {t['NDF']:.0f} г ({100*t['NDF']/(t['dm']*1000):.1f}% от СВ)"
        )
        if r["corrections"]:
            lines.append("Корректировки:")
            for c in r["corrections"]:
                lines.append(f"  • {c}")

    lines.append("")
    lines.append(
        "Дай финальный вывод: какой образец выбрать для этой коровы, "
        "какие риски учесть, что конкретно добавить/убрать из рациона."
    )
    return "\n".join(lines)


def get_ai_recommendation(context: str, force_refresh: bool = False) -> str:
    """Обёртка с кэшированием. force_refresh=True — принудительно перезапросить."""
    if force_refresh:
        st.cache_data.clear()
    key = _make_cache_key(context)
    return _call_api(key, context)
