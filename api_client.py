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
- параметры двух гибридов (Сингента vs конкурент): урожайность, затраты, качество
- результаты лабораторного анализа силоса (если есть)
- расчёт экономии от выбора лучшего гибрида
- выбранный сценарий (фиксированная площадь или фиксированная потребность)

Твоя задача — дать краткий, конкретный, практичный вывод СТРОГО в таком виде:

## 1. Краткий вывод
Одно предложение: какой гибрид выгоднее и на сколько (в валюте расчёта).

## 2. Экономический расчёт
Для сценария «фиксированная потребность»:
- Экономия затрат на выращивание: X.
- Экономия на кормлении: Y.
- Итого: Z.

Для сценария «фиксированная площадь»:
- Экономия затрат: X.
- Стоимость излишка силоса: Y.
- Экономия на кормлении: Z.
- Итого: W.

## 3. Что даёт Сингента (или конкурент — если он выигрывает)
3–4 конкретных пункта с цифрами: разница в урожайности СВ, разница в ОЭ,
разница в площади или излишке, разница в затратах.

## 4. Ключевые цифры
Только конкретные показатели из расчёта. Что дало основной вклад в экономию.
2–3 цифры. Без оговорок и предположений.

## 5. Рекомендация
Одна фраза: сеять X / не сеять / данные требуют уточнения.

КРИТИЧЕСКИ ВАЖНО:
- Только русскими буквами.
- Конкретные цифры из расчёта.
- НЕ упоминай погоду, форс-мажоры, «может измениться»,
  «погодные условия могут нивелировать», «требует проверки в поле».
- Только прямой анализ тех цифр, которые тебе переданы.
- Если данных мало — коротко скажи, чего не хватает, без общих фраз.
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
    scenario = econ_result.get("scenario", "demand")

    if scenario == "area":
        scenario_label = "Фиксированная площадь"
    else:
        scenario_label = "Фиксированная потребность"

    lines = [
        "=== СРАВНЕНИЕ ДВУХ ГИБРИДОВ КУКУРУЗЫ НА СИЛОС ===",
        f"СЦЕНАРИЙ: {scenario_label}",
        "",
        f"--- {silenta_name} (Гибрид Сингента) ---",
        f"Урожайность ЗМ: {s['yield_green']} ц/га",
        f"Содержание СВ: {s['dm_pct']} %",
        f"Урожайность СВ: {s['dm_yield']:.1f} ц/га",
        f"Выход ОЭ: {s['me_per_ha']:,.0f} МДж/га".replace(",", " "),
        f"ОЭ: {s['me']} МДж/кг СВ",
    ]
    if silenta_extra:
        lines.append("Лабораторный анализ (из силоса):")
        lines.append(f"  крахмал={silenta_extra.get('starch')} г/кг СВ, "
                     f"НДК={silenta_extra.get('NDF')} г/кг СВ, "
                     f"СП={silenta_extra.get('CP')} г/кг СВ, "
                     f"перев. ОВ={silenta_extra.get('dOM')}%")

    lines.extend([
        "",
        f"--- {competitor_name} (Гибрид конкурента) ---",
        f"Урожайность ЗМ: {c['yield_green']} ц/га",
        f"Содержание СВ: {c['dm_pct']} %",
        f"Урожайность СВ: {c['dm_yield']:.1f} ц/га",
        f"Выход ОЭ: {c['me_per_ha']:,.0f} МДж/га".replace(",", " "),
        f"ОЭ: {c['me']} МДж/кг СВ",
    ])
    if competitor_extra:
        lines.append("Лабораторный анализ (из силоса):")
        lines.append(f"  крахмал={competitor_extra.get('starch')} г/кг СВ, "
                     f"НДК={competitor_extra.get('NDF')} г/кг СВ, "
                     f"СП={competitor_extra.get('CP')} г/кг СВ, "
                     f"перев. ОВ={competitor_extra.get('dOM')}%")

    lines.append("")
    lines.append("=== РАСЧЁТ ===")

    if scenario == "area":
        # Сценарий "площадь"
        same_area = econ_result.get("same_area", 0)
        lines.extend([
            f"Площадь посева: {same_area:.1f} га (одинаковая для обоих)",
            f"Затраты — {silenta_name}: "
            f"{econ_result.get('cost_silenta', 0):,.0f}".replace(",", " "),
            f"Затраты — {competitor_name}: "
            f"{econ_result.get('cost_competitor', 0):,.0f}".replace(",", " "),
            f"Экономия затрат: "
            f"{econ_result.get('saving_field', 0):,.0f}".replace(",", " "),
            f"Излишек СВ у Сингенты: "
            f"{econ_result.get('surplus_dm_t', 0):.1f} т СВ",
            f"Излишек ЗМ: {econ_result.get('surplus_gm_t', 0):.1f} т",
            f"Эквивалент зерна по ОЭ: "
            f"{econ_result.get('surplus_grain_t', 0):.1f} т зерна",
        ])
    else:
        # Сценарий "потребность"
        lines.extend([
            f"Площадь — {silenta_name}: "
            f"{econ_result.get('silenta_area', s['area']):.1f} га",
            f"Площадь — {competitor_name}: "
            f"{econ_result.get('competitor_area', c['area']):.1f} га",
            f"Освобождено площади: "
            f"{econ_result.get('freed_area', 0):.1f} га",
            f"Затраты — {silenta_name}: "
            f"{s['total_cost']:,.0f}".replace(",", " "),
            f"Затраты — {competitor_name}: "
            f"{c['total_cost']:,.0f}".replace(",", " "),
            f"Экономия затрат: "
            f"{econ_result.get('saving_field', 0):,.0f}".replace(",", " "),
        ])

    lines.append("")
    lines.append(
        "Выдай отчёт СТРОГО по структуре из системного промпта. "
        "Опирайся на конкретные цифры. Если данные из лабораторного "
        "анализа противоречат экономическим — укажи это."
    )
    return "\n".join(lines)


def get_economics_ai_recommendation(context: str,
                                      force_refresh: bool = False) -> str:
    if force_refresh:
        st.cache_data.clear()
    key = _make_cache_key("econ_" + context)
    return _call_api_with_prompt(key, context, ECON_SYSTEM_PROMPT)
