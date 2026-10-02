"""Экономический расчёт выращивания силосной кукурузы + экономия на кормах.
Все суммы — в одной валюте расчёта. Внутренние формулы в центнерах (1 т = 10 ц).
"""

GRAIN_ME = 12.835  # МДж/кг ОЭ зерна кукурузы (СВ 85%)


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


# ================== РАСЧЁТ ОДНОГО ГИБРИДА ==================

def _calc_one(p: dict) -> dict:
    silo_demand  = _f(p.get("silo_demand"), 0)
    yield_green  = _f(p.get("yield_green"), 0)
    seeding_rate = _f(p.get("seeding_rate"), 0)
    seed_price   = _f(p.get("seed_price"), 0)
    field_cost   = _f(p.get("field_cost"), 0)
    dm_pct       = _f(p.get("dm_pct"), 35)
    me           = _f(p.get("me"), 11.0)

    area = silo_demand / yield_green if yield_green > 0 else 0
    seed_cost_per_ha = (seed_price / 80) * seeding_rate / 1000
    total_cost = (field_cost + seed_cost_per_ha) * area
    dm_yield = yield_green * dm_pct / 100
    dm_total = dm_yield * area
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


# ================== СРАВНЕНИЕ ГИБРИДОВ ==================

def calculate_economics(silenta: dict, competitor: dict,
                         scenario: str = "demand",
                         fixed_area_ha: float = None) -> dict:
    """
    scenario:
        "area"   — фиксированная площадь. Считаем экономию затрат и излишек.
        "demand" — фиксированная потребность. Считаем только экономию затрат.
    fixed_area_ha — площадь для сценария "area".
                    Если None — используем площадь конкурента.
    """
    s = _calc_one(silenta)
    c = _calc_one(competitor)

    if scenario == "area":
        same_area = fixed_area_ha if fixed_area_ha else c["area"]

        cost_silenta = (s["seed_cost_per_ha"] + s["field_cost"]) * same_area
        cost_competitor = (c["seed_cost_per_ha"] + c["field_cost"]) * same_area
        saving_field = cost_competitor - cost_silenta

        # Излишек силоса у Силенты
        dm_silenta_c   = s["dm_yield"] * same_area
        dm_competitor_c = c["dm_yield"] * same_area
        dm_surplus_t = (dm_silenta_c - dm_competitor_c) / 10

        dm_pct = s["dm_pct"] / 100
        gm_surplus_t = dm_surplus_t / dm_pct if dm_pct > 0 else 0

        me_surplus_mj = dm_surplus_t * 1000 * s["me"]
        grain_equiv_t = me_surplus_mj / GRAIN_ME / 1000

        return {
            "scenario": "area",
            "silenta": s,
            "competitor": c,
            "same_area": same_area,
            "saving_field": saving_field,
            "cost_silenta": cost_silenta,
            "cost_competitor": cost_competitor,
            "surplus_dm_t": dm_surplus_t,
            "surplus_gm_t": gm_surplus_t,
            "surplus_me_mj": me_surplus_mj,
            "surplus_grain_t": grain_equiv_t,
        }
    else:  # "demand"
        saving_field = c["total_cost"] - s["total_cost"]
        freed_area = c["area"] - s["area"]

        return {
            "scenario": "demand",
            "silenta": s,
            "competitor": c,
            "saving_field": saving_field,
            "freed_area": freed_area,
            "silenta_area": s["area"],
            "competitor_area": c["area"],
        }


# ================== ЭКОНОМИЯ НА КОРМАХ ==================

def calc_feed_economics(silenta_params: dict,
                         competitor_params: dict,
                         live_weight: float,
                         milk_yield: float,
                         n_cows: int,
                         conc_price_per_t: float,
                         silo_price_per_t: float,
                         hay_price_per_t: float = 0.0,
                         haylage_price_per_t: float = 0.0,
                         feeds_lib: dict = None) -> dict:
    from ration_calculator import calculate_ration

    r1 = calculate_ration(silenta_params, live_weight, milk_yield,
                          feeds_lib=feeds_lib)
    r2 = calculate_ration(competitor_params, live_weight, milk_yield,
                          feeds_lib=feeds_lib)

    def _nat(ration_dict, feed):
        return ration_dict["ration"].get(feed, {}).get("nat", 0.0)

    silo1_nat = _nat(r1, "силос")
    silo2_nat = _nat(r2, "силос")
    conc1_nat = _nat(r1, "комбикорм")
    conc2_nat = _nat(r2, "комбикорм")
    hay1_nat  = _nat(r1, "сено")
    hay2_nat  = _nat(r2, "сено")
    haylage1_nat = _nat(r1, "сенаж")
    haylage2_nat = _nat(r2, "сенаж")

    delta_silo_nat    = silo2_nat - silo1_nat
    delta_conc_nat    = conc2_nat - conc1_nat
    delta_hay_nat     = hay2_nat - hay1_nat
    delta_haylage_nat = haylage2_nat - haylage1_nat

    saving_silo_cow_day    = delta_silo_nat * silo_price_per_t / 1000
    saving_conc_cow_day    = delta_conc_nat * conc_price_per_t / 1000
    saving_hay_cow_day     = delta_hay_nat * hay_price_per_t / 1000
    saving_haylage_cow_day = delta_haylage_nat * haylage_price_per_t / 1000

    saving_silo_day    = saving_silo_cow_day * n_cows
    saving_conc_day    = saving_conc_cow_day * n_cows
    saving_hay_day     = saving_hay_cow_day * n_cows
    saving_haylage_day = saving_haylage_cow_day * n_cows

    total_feed_day = (saving_silo_day + saving_conc_day
                       + saving_hay_day + saving_haylage_day)
    total_feed_year = total_feed_day * 365

    return {
        "ration_silenta": r1,
        "ration_competitor": r2,
        "silo1_nat": silo1_nat, "silo2_nat": silo2_nat,
        "conc1_nat": conc1_nat, "conc2_nat": conc2_nat,
        "hay1_nat": hay1_nat, "hay2_nat": hay2_nat,
        "haylage1_nat": haylage1_nat, "haylage2_nat": haylage2_nat,
        "delta_silo_nat": delta_silo_nat,
        "delta_conc_nat": delta_conc_nat,
        "delta_hay_nat": delta_hay_nat,
        "delta_haylage_nat": delta_haylage_nat,
        "saving_silo_cow_day": saving_silo_cow_day,
        "saving_conc_cow_day": saving_conc_cow_day,
        "saving_hay_cow_day": saving_hay_cow_day,
        "saving_haylage_cow_day": saving_haylage_cow_day,
        "saving_silo_day": saving_silo_day,
        "saving_silo_year": saving_silo_day * 365,
        "saving_conc_day": saving_conc_day,
        "saving_conc_year": saving_conc_day * 365,
        "saving_hay_day": saving_hay_day,
        "saving_hay_year": saving_hay_day * 365,
        "saving_haylage_day": saving_haylage_day,
        "saving_haylage_year": saving_haylage_day * 365,
        "total_feed_day": total_feed_day,
        "total_feed_year": total_feed_year,
        "n_cows": n_cows,
    }
