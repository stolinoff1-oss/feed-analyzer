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
