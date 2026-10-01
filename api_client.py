import requests
import streamlit as st
import hashlib


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
- Обрати внимание на связь: какой силос даёт меньшую долю концентратов в рационе.

КРИТИЧЕСКИ ВАЖНО:
- Пиши ТОЛЬКО русскими буквами. НИКАКОЙ транслитерации (не "Pachet", а "Расчёт").
- Используй русские буквы С, В, М, Д, Ж (не латинские C, B, M, D, X).
- Без воды, только конкретика и цифры.
- Не повторяй одинаковые фразы.
- Если образец слабый — прямо говори об этом.
- Учитывай адаптивную структуру рациона (силос vs комбикорм) в выводах.
"""


AIAI_API_URL = "https://api.aiai.by/v1/chat/completions"
AIAI_MODEL = "deepseek-chat"


def _make_cache_key(context: str) -> str:
    return hashlib.sha256(context.encode("utf-8")).hexdigest()


@st.cache_data(ttl=3600, show_spinner=False)
def _call_api(context_hash: str, context: str) -> str:
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
        r = requests.post(AIAI_API_URL, headers=headers, json=payload, timeout=180)
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



# ================== ЭКОНОМИЧЕСКИЙ AI ==================

ECON_SYSTEM_PROMPT = """Ты — экономист-агроном, специалист по выращиванию кукурузы на силос.
Ты получаешь:
- параметры двух гибридов (Сингента vs конкурент): урожайность, затраты, качество
- результаты лабораторного анализа силоса (если есть)
- расчёт экономии от выбора лучшего гибрида

Твоя задача — дать краткий, конкретный, практичный вывод СТРОГО в таком виде:

## 1. Краткий вывод
Одно предложение: какой гибрид выгоднее и на сколько рублей.

## 2. Экономический расчёт
- Экономия затрат: X руб (за счёт меньшей площади).
- Экономия на зерне: Y руб (за счёт разницы ОЭ).
- Общая экономия: Z руб.
- На гектар: W руб/га.

## 3. Что даёт Сингента (или конкурент — если он выигрывает)
3–4 конкретных пункта с цифрами из расчёта.

## 4. Риски и оговорки
2–3 пункта: что может изменить вывод (цена зерна, урожайность, погода).
Будь честен: если разница незначительная — скажи прямо.

## 5. Рекомендация
Одна фраза: сеять X / не сеять / требуется уточнить.

КРИТИЧЕСКИ ВАЖНО:
- Только русскими буквами.
- Конкретные цифры из расчёта.
- Если данных мало — скажи, чего не хватает.
- Не выдумывай цифры.
"""


def build_economics_context(econ_result: dict,
                             silenta_name: str,
                             competitor_name: str,
                             silenta_extra: dict = None,
                             competitor_extra: dict = None) -> str:
    """Формирует контекст для AI по экономике."""
    s = econ_result["silenta"]
    c = econ_result["competitor"]

    lines = [
        "=== СРАВНЕНИЕ ДВУХ ГИБРИДОВ КУКУРУЗЫ НА СИЛОС ===",
        "",
        f"--- {silenta_name} (Гибрид Сингента) ---",
        f"Урожайность ЗМ: {s['yield_green']} ц/га",
        f"Содержание СВ: {s['dm_pct']} %",
        f"Урожайность СВ: {s['dm_yield']:.1f} ц/га",
        f"Площадь сева: {s['area']:.1f} га",
        f"Затраты на всю площадь: {s['total_cost']:,.0f} руб".replace(",", " "),
        f"Выход ОЭ: {s['me_per_ha']:,.0f} МДж/га".replace(",", " "),
        f"ОЭ: {s['me']} МДж/кг СВ",
    ]
    if silenta_extra:
        lines.append(f"Лабораторный анализ (из силоса):")
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
        f"Площадь сева: {c['area']:.1f} га",
        f"Затраты на всю площадь: {c['total_cost']:,.0f} руб".replace(",", " "),
        f"Выход ОЭ: {c['me_per_ha']:,.0f} МДж/га".replace(",", " "),
        f"ОЭ: {c['me']} МДж/кг СВ",
    ])
    if competitor_extra:
        lines.append(f"Лабораторный анализ (из силоса):")
        lines.append(f"  крахмал={competitor_extra.get('starch')} г/кг СВ, "
                     f"НДК={competitor_extra.get('NDF')} г/кг СВ, "
                     f"СП={competitor_extra.get('CP')} г/кг СВ, "
                     f"перев. ОВ={competitor_extra.get('dOM')}%")

    lines.extend([
        "",
        "=== ЭКОНОМИЧЕСКИЙ РАСЧЁТ ===",
        f"Освобождено площади: {econ_result['freed_area']:.1f} га",
        f"Экономия затрат на выращивание: "
        f"{econ_result['saving_field']:,.0f} руб".replace(",", " "),
        f"Разница выхода ОЭ: "
        f"{econ_result['delta_me_per_ha']:,.0f} МДж/га".replace(",", " "),
        f"Эквивалент кукурузного зерна: "
        f"{econ_result['grain_equiv_per_ha']:,.0f} кг/га".replace(",", " "),
        f"Цена зерна: {econ_result['grain_price']:,.0f} руб/т".replace(",", " "),
        f"Экономия на зерне: "
        f"{econ_result['saving_grain']:,.0f} руб".replace(",", " "),
        f"ОБЩАЯ ЭКОНОМИЯ: "
        f"{econ_result['total_saving']:,.0f} руб".replace(",", " "),
        f"Экономия на гектар: "
        f"{econ_result['total_saving_per_ha']:,.0f} руб/га".replace(",", " "),
        "",
        "Выдай отчёт СТРОГО по структуре из системного промпта. "
        "Опирайся на конкретные цифры. Если данные из лабораторного "
        "анализа противоречат экономическим — укажи это."
    ])
    return "\n".join(lines)


def get_economics_ai_recommendation(context: str,
                                      force_refresh: bool = False) -> str:
    """AI-вывод по экономике. Использует тот же ключ AIAI.BY."""
    if force_refresh:
        st.cache_data.clear()
    key = _make_cache_key("econ_" + context)
    return _call_api_with_prompt(key, context, ECON_SYSTEM_PROMPT)


@st.cache_data(ttl=3600, show_spinner=False)
def _call_api_with_prompt(context_hash: str, context: str,
                            system_prompt: str) -> str:
    """Универсальный вызов с произвольным системным промптом."""
    api_key = st.secrets.get("AIAI_API_KEY", "")
    if not api_key or not api_key.startswith("sk-"):
        return ("⚠️ API-ключ AIAI.BY не задан в Secrets.\n\n"
                "Откройте Manage app → ⋮ → Settings → Secrets и добавьте "
                'строку: AIAI_API_KEY = "sk-vedai-ваш-ключ"')

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
            return "❌ Ошибка 401: Неверный ключ AIAI.BY."
        if r.status_code == 402:
            return "❌ Ошибка 402: Закончился баланс AIAI.BY."
        if r.status_code >= 400:
            return f"❌ Ошибка {r.status_code}: {r.text[:500]}"
        return r.json()["choices"][0]["message"]["content"]
    except requests.exceptions.Timeout:
        return "⏱️ Таймаут: сервер не ответил за 3 минуты."
    except Exception as e:
        return f"❌ Ошибка: {e}"
