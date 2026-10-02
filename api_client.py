import requests
import streamlit as st
import hashlib


# ================== ЗООТЕХНИЧЕСКИЙ AI ==================

SYSTEM_PROMPT = """Ты — опытный зоотехник-консультант по кормлению молочного скота.
Ты получаешь:
- параметры конкретной коровы (живая масса, удой),
- результаты лабораторного анализа нескольких образцов кукурузного силоса,
- расчёт рационов для КАЖДОГО образца, где доля силоса АДАПТИРУЕТСЯ под НДК.

Твоя задача — дать структурированный отчёт СТРОГО в таком виде:

## 1. Краткий обзор
Одно-два предложения: сколько образцов, для какой коровы анализ.

## 2. Сводная таблица по всем образцам
Markdown-таблица со столбцами:
| Образец | Балл | NEL-VC | Крахмал | НДК | RNB | Категория | Краткий вывод |

Категория: «Премиум», «Хороший», «Средний», «Слабый».

## 3. Рекомендации по каждому образцу
Для КАЖДОГО образца:

**Образец X — [краткое имя]**
- Плюсы: 2–3 пункта с цифрами.
- Минусы: 1–3 пункта с цифрами.
- Структура рациона: доля силоса и комбикорма в % от СВ, кг жира и шрота.
- Для каких коров: высокопродуктивных / средних / низкопродуктивных / сухостойных.
- Что учесть: конкретные корректировки (буферы, жир, шрот, патока) с дозировками.
- Итог: одна фраза — брать / брать с оговорками / не использовать.

## 4. Итоговый рейтинг
Нумерованный список: от лучшего к худшему с одной фразой обоснования.

## 5. Общие выводы
- Оптимальный, запасной, исключить.
- Общие рекомендации по рациону.

КРИТИЧЕСКИ ВАЖНО:
- Только русскими буквами. НИКАКОЙ транслитерации.
- Конкретные цифры из расчёта.
- Без воды.
- Если образец слабый — прямо говори об этом.
"""


# ================== ЭКОНОМИЧЕСКИЙ AI ==================

ECON_SYSTEM_PROMPT = """Ты — экономист-агроном, специалист по выращиванию кукурузы на силос.
Ты получаешь:
- сценарий (по поголовью или по площади)
- параметры двух гибридов (Сингента vs конкурент)
- результаты лабораторного анализа силоса (если есть)
- расчёт экономии

Твоя задача — дать краткий, конкретный вывод СТРОГО в таком виде:

## 1. Краткий вывод
Одно предложение: какой гибрид выгоднее и на сколько (в валюте расчёта).
ОБЯЗАТЕЛЬНО указывай масштаб: «на N голов» или «на M га».

## 2. Экономический расчёт
Сценарий «поголовье»:
- Потребность: X т ЗМ на N голов
- Экономия затрат на выращивание: Y (на площади под этот объём)
- Экономия на кормлении: Z (на N голов)
- Итого: W

Сценарий «площадь»:
- Площадь: M га
- Затраты — Сингента: X, конкурент: Y
- Экономия затрат: Z
- Излишек силоса: W (при наличии)
- Итого: V

## 3. Что даёт Сингента (или конкурент)
3–4 конкретных пункта с цифрами. Указывай масштаб.

## 4. Ключевые цифры
2–3 ключевых показателя, определивших результат.

## 5. Рекомендация
Одна фраза.

КРИТИЧЕСКИ ВАЖНО:
- Только русскими буквами.
- ВСЕГДА указывай масштаб: поголовье или площадь.
- Конкретные цифры.
- НЕ упоминай погоду, «может измениться», «требует проверки в поле».
- Не выдумывай цифры.
"""


AIAI_API_URL = "https://api.aiai.by/v1/chat/completions"
AIAI_MODEL = "deepseek-chat"


def _make_cache_key(context: str) -> str:
    return hashlib.sha256(context.encode("utf-8")).hexdigest()


@st.cache_data(ttl=3600, show_spinner=False)
def _call_api_with_prompt(context_hash: str, context: str,
                            system_prompt: str) -> str:
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
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context},
        ],
        "temperature": 0.3,
    }
    try:
        r = requests.post(AIAI_API_URL, headers=headers, json=payload,
                          timeout=180)
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
        return "⏱️ Таймаут: сервер не ответил за 3 минуты."
    except Exception as e:
        return f"❌ Ошибка: {e}"


def _call_api(context_hash: str, context: str) -> str:
    return _call_api_with_prompt(context_hash, context, SYSTEM_PROMPT)


# ================== ЗООТЕХНИЧЕСКИЙ КОНТЕКСТ ==================

def build_context(analysis: dict, rations: dict,
                  live_weight: float, milk_yield: float) -> str:
    lines = [
        "=== ПАРАМЕТРЫ КОРОВЫ ===",
        f"Живая масса: {live_weight} кг",
        f"Суточный удой: {milk_yield} кг",
        "",
        f"=== ОБРАЗЦОВ В АНАЛИЗЕ: {len(analysis['ratings'])} ===",
        "",
        "=== РЕЗУЛЬТАТЫ АНАЛИЗА (все образцы по рейтингу) ===",
        "Формат: имя | DM | крахмал | сахар | НДК | КДК | "
        "перев.ОВ% | NEL | NEL-VC | nXP | RNB | структурный | балл",
    ]
    for i, s in enumerate(analysis["ratings"], 1):
        lines.append(
            f"{i}. {s['name']} | DM={s.get('DM')} | "
            f"крахмал={s.get('starch')} | сахар={s.get('sugar')} | "
            f"НДК={s.get('NDF')} | КДК={s.get('ADF')} | "
            f"перев.ОВ={s.get('dOM')}% | NEL={s.get('NEL')} | "
            f"NEL-VC={s.get('NEL_VC')} | nXP={s.get('nXP')} | "
            f"RNB={s.get('RNB')} | структ={s.get('structure')} | "
            f"балл={s.get('score')}"
        )

    lines.append("")
    lines.append("=== РАСЧЁТ РАЦИОНОВ (адаптивный по НДК) ===")
    lines.append("ВАЖНО: доля силоса подбирается так, чтобы НДК в рационе "
                 "не превышала 34% СВ. Для силосов с высокой НДК доля "
                 "силоса меньше, а комбикорма — больше.")

    for name, r in rations.items():
        n = r["norms"]
        t = r["total"]
        c = r["composition"]
        lines.append(
            f"\n--- {name} ---\n"
            f"Норма: NEL={n['NEL']} МДж, nXP={n['nXP']} г, СВ={n['DM']} кг\n"
            f"Структура: силос {c['silo_pct']:.0f}% СВ, "
            f"сено {c['hay_pct']:.0f}%, сенаж {c['haylage_pct']:.0f}%, "
            f"комбикорм {c['conc_pct']:.0f}% СВ\n"
            f"Жир: {c['fat_kg']:.2f} кг, шрот: {c['soy_dm']:.2f} кг СВ\n"
            f"Факт: NEL={t['NEL']:.1f}, nXP={t['nXP']:.0f}, "
            f"НДК={c['ndf_pct']:.1f}% СВ"
        )
        if r["warnings"]:
            for w in r["warnings"]:
                lines.append(f"  ⚠️ {w}")

    lines.append("")
    lines.append(
        "Выдай отчёт СТРОГО по структуре из системного промпта: "
        "сводная таблица по ВСЕМ образцам, затем блок по каждому образцу, "
        "итоговый рейтинг и общие выводы. Не пропускай ни один образец. "
        "Учитывай разницу в структуре рационов (доля силоса vs комбикорма) "
        "при выводах — это ключевой показатель."
    )
    return "\n".join(lines)


def get_ai_recommendation(context: str, force_refresh: bool = False) -> str:
    if force_refresh:
        st.cache_data.clear()
    key = _make_cache_key(context)
    return _call_api(key, context)


# ================== ЭКОНОМИЧЕСКИЙ КОНТЕКСТ ==================

def build_economics_context(econ_result: dict,
                             silenta_name: str,
                             competitor_name: str,
                             silenta_extra: dict = None,
                             competitor_extra: dict = None) -> str:
    """Формирует контекст для AI по экономике с учётом выбранного сценария."""
    s = econ_result["silenta"]
    c = econ_result["competitor"]
    scenario = econ_result.get("scenario", "herd")

    lines = ["=== СРАВНЕНИЕ ДВУХ ГИБРИДОВ КУКУРУЗЫ НА СИЛОС ==="]

    if scenario == "herd":
        lines.append("СЦЕНАРИЙ: Поголовье (нужно прокормить N голов)")
        lines.append(f"Потребность: "
                     f"{econ_result.get('silo_demand_t', 0):.1f} т ЗМ/год")
    else:
        lines.append("СЦЕНАРИЙ: Фиксированная площадь")
        lines.append(f"Площадь: {econ_result.get('same_area', 0):.1f} га")

    lines.append("")
    lines.append(f"--- {silenta_name} (Гибрид Сингента) ---")
    lines.append(f"Урожайность ЗМ: {s['yield_green']} ц/га")
    lines.append(f"Содержание СВ: {s['dm_pct']} %")
    lines.append(f"Урожайность СВ: {s['dm_yield']:.1f} ц/га")
    if scenario == "herd":
        lines.append(f"Площадь сева: {s['area']:.1f} га")
        lines.append(f"Затраты на всю площадь: {s['total_cost']:,.0f}"
                     .replace(",", " "))
    else:
        lines.append(f"Валовый сбор СВ: "
                     f"{s['dm_yield'] * econ_result.get('same_area', 0):,.0f} ц"
                     .replace(",", " "))
        lines.append(f"Затраты: "
                     f"{econ_result.get('cost_silenta', 0):,.0f}"
                     .replace(",", " "))
    lines.append(f"Выход ОЭ: {s['me_per_ha']:,.0f} МДж/га".replace(",", " "))
    lines.append(f"ОЭ: {s['me']} МДж/кг СВ")
    if silenta_extra:
        lines.append("Из анализа:")
        lines.append(f"  крахмал={silenta_extra.get('starch')} г/кг СВ, "
                     f"НДК={silenta_extra.get('NDF')} г/кг СВ, "
                     f"СП={silenta_extra.get('CP')} г/кг СВ, "
                     f"перев. ОВ={silenta_extra.get('dOM')}%")

    lines.append("")
    lines.append(f"--- {competitor_name} (Гибрид конкурента) ---")
    lines.append(f"Урожайность ЗМ: {c['yield_green']} ц/га")
    lines.append(f"Содержание СВ: {c['dm_pct']} %")
    lines.append(f"Урожайность СВ: {c['dm_yield']:.1f} ц/га")
    if scenario == "herd":
        lines.append(f"Площадь сева: {c['area']:.1f} га")
        lines.append(f"Затраты на всю площадь: {c['total_cost']:,.0f}"
                     .replace(",", " "))
    else:
        lines.append(f"Валовый сбор СВ: "
                     f"{c['dm_yield'] * econ_result.get('same_area', 0):,.0f} ц"
                     .replace(",", " "))
        lines.append(f"Затраты: "
                     f"{econ_result.get('cost_competitor', 0):,.0f}"
                     .replace(",", " "))
    lines.append(f"Выход ОЭ: {c['me_per_ha']:,.0f} МДж/га".replace(",", " "))
    lines.append(f"ОЭ: {c['me']} МДж/кг СВ")
    if competitor_extra:
        lines.append("Из анализа:")
        lines.append(f"  крахмал={competitor_extra.get('starch')} г/кг СВ, "
                     f"НДК={competitor_extra.get('NDF')} г/кг СВ, "
                     f"СП={competitor_extra.get('CP')} г/кг СВ, "
                     f"перев. ОВ={competitor_extra.get('dOM')}%")

    lines.append("")
    lines.append("=== РАСЧЁТ ===")

    if scenario == "herd":
        lines.append(f"Площадь — Сингента: "
                     f"{econ_result.get('silenta_area', s['area']):.1f} га")
        lines.append(f"Площадь — конкурент: "
                     f"{econ_result.get('competitor_area', c['area']):.1f} га")
        lines.append(f"Освобождено площади: "
                     f"{econ_result.get('freed_area', 0):.1f} га")
        lines.append(f"Экономия затрат на выращивание: "
                     f"{econ_result.get('saving_field', 0):,.0f}"
                     .replace(",", " "))
    else:
        lines.append(f"Затраты — Сингента: "
                     f"{econ_result.get('cost_silenta', 0):,.0f}"
                     .replace(",", " "))
        lines.append(f"Затраты — конкурент: "
                     f"{econ_result.get('cost_competitor', 0):,.0f}"
                     .replace(",", " "))
        lines.append(f"Экономия затрат: "
                     f"{econ_result.get('saving_field', 0):,.0f}"
                     .replace(",", " "))
        lines.append(f"Излишек СВ у Сингенты: "
                     f"{econ_result.get('surplus_dm_t', 0):.1f} т СВ")
        lines.append(f"Излишек ЗМ: "
                     f"{econ_result.get('surplus_gm_t', 0):.1f} т ЗМ")

    lines.append("")
    lines.append(
        "Выдай отчёт СТРОГО по структуре из системного промпта. "
        "ОБЯЗАТЕЛЬНО указывай масштаб (поголовье или площадь) в каждом выводе."
    )
    return "\n".join(lines)


def get_economics_ai_recommendation(context: str,
                                      force_refresh: bool = False) -> str:
    if force_refresh:
        st.cache_data.clear()
    key = _make_cache_key("econ_" + context)
    return _call_api_with_prompt(key, context, ECON_SYSTEM_PROMPT)
