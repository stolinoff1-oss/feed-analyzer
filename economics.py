"""Экономический расчёт выращивания силосной кукурузы.
Логика повторяет Excel-калькулятор «Рентабельность выращивания».
"""

# Константа: ОЭ 1 кг кукурузного зерна при СВ 85% (МДж/кг)
GRAIN_ME = 12.835


def _f(x, default=0.0):
    if x is None:
        return default
    try:
        f = float(x)
        if f != f:
            return default
        return f
    except (TypeError, ValueError):
        return default


def _calc_one(p: dict) -> dict:
    """Расчёт одного гибрида."""
    silo_demand = _f(p.get("silo_demand"), 0)   # ц/год
    yield_green = _f(p.get("yield_green"), 0)   # ц/га ЗМ
    seeding_rate = _f(p.get("seeding_rate"), 0) # шт/га
    seed_price = _f(p.get("seed_price"), 0)     # руб/п.е. (80 тыс. семян)
    field_cost = _f(p.get("field_cost"), 0)     # руб/га
    dm_pct = _f(p.get("dm_pct"), 35)            # %
    me = _f(p.get("me"), 11.0)                  # МДж/кг СВ

    # 1. Площадь сева (га)
    area = silo_demand / yield_green if yield_green > 0 else 0

    # 2. Затраты на семена (руб/га)
    # (Стоимость 1 п.е. / 80 тыс. семян) × Норма высева / 1000
    seed_cost_per_ha = (seed_price / 80) * seeding_rate / 1000

    # 3. Затраты на всю площадь (руб)
    total_cost = (field_cost + seed_cost_per_ha) * area

    # 4. Урожайность СВ (ц/га)
    dm_yield = yield_green * dm_pct / 100

    # 5. Валовый сбор СВ (ц)
    dm_total = dm_yield * area

    # 6. Выход ОЭ (МДж/га)
    # me (МДж/кг) × dm_yield (ц/га) × 100 (кг/ц)
    me_per_ha = me * dm_yield * 100

    return {
        "area": area,
        "seed_cost_per_ha": seed_cost_per_ha,
        "field_cost": field_cost,
        "total_cost": total_cost,
        "dm_yield": dm_yield,
        "dm_total": dm_total,
        "me_per_ha": me_per_ha,
        "me": me,
        "dm_pct": dm_pct,
        "yield_green": yield_green,
    }


def calculate_economics(silenta: dict, competitor: dict) -> dict:
    """
    silenta, competitor — словари с параметрами обоих гибридов.

    Возвращает:
    - silenta, competitor — детальные результаты
    - saving_field — экономия затрат на выращивание (руб)
    - freed_area — освобождено площади (га)
    - delta_me_per_ha — разница выхода ОЭ (МДж/га)
    - grain_equiv_per_ha — эквивалент кукурузного зерна (кг/га)
    - saving_grain — экономия на зерне (руб)
    - total_saving — общая экономия (руб)
    - total_saving_per_ha — экономия на гектар (руб/га)
    """
    s = _calc_one(silenta)
    c = _calc_one(competitor)

    saving_field = c["total_cost"] - s["total_cost"]
    freed_area = c["area"] - s["area"]

    delta_me = s["me_per_ha"] - c["me_per_ha"]
    grain_equiv = delta_me / GRAIN_ME if GRAIN_ME else 0  # кг/га

    grain_price = _f(silenta.get("grain_price"), 10000)   # руб/т
    saving_grain = grain_equiv * grain_price / 1000 * c["area"]  # руб

    total_saving = saving_field + saving_grain
    total_saving_per_ha = total_saving / c["area"] if c["area"] else 0

    return {
        "silenta": s,
        "competitor": c,
        "saving_field": saving_field,
        "freed_area": freed_area,
        "delta_me_per_ha": delta_me,
        "grain_equiv_per_ha": grain_equiv,
        "grain_price": grain_price,
        "saving_grain": saving_grain,
        "total_saving": total_saving,
        "total_saving_per_ha": total_saving_per_ha,
    }
