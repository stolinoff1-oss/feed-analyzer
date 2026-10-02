"""Экономический расчёт выращивания силосной кукурузы.
Два сценария: поголовье (нужно прокормить N голов) и площадь (есть M га).
Все суммы — в валюте расчёта. Внутренние формулы в центнерах (1 т = 10 ц).
"""

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


def calc_demand_from_herd(n_cows: float, silo_per_cow_kg: float,
                           days: float) -> float:
    """Потребность в силосе в т ЗМ.
    n_cows — голов
    silo_per_cow_kg — кг ЗМ на 1 голову в сутки
    days — дней кормления в году
    """
    return _f(n_cows) * _f(silo_per_cow_kg) * _f(days) / 1000.0


def _calc_one(p: dict, silo_demand_c: float = 0) -> dict:
    """Расчёт одного гибрида.
    silo_demand_c — потребность в силосе, ц ЗМ (0 = не использовать).
    """
    yield_green  = _f(p.get("yield_green"), 0)
    seeding_rate = _f(p.get("seeding_rate"), 0)
    seed_price   = _f(p.get("seed_price"), 0)
    field_cost   = _f(p.get("field_cost"), 0)
    dm_pct       = _f(p.get("dm_pct"), 35)
    me           = _f(p.get("me"), 11.0)

    area = silo_demand_c / yield_green if yield_green > 0 and silo_demand_c > 0 else 0
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


def calculate_economics(silenta: dict, competitor: dict,
                         scenario: str,
                         silo_demand_t: float = None,
                         fixed_area_ha: float = None) -> dict:
    """
    scenario:
        "herd" — потребность известна (т ЗМ), площади разные.
        "area" — площадь фиксирована, излишек у более урожайного.

    silo_demand_t — потребность в силосе, т ЗМ (для сценария herd)
    fixed_area_ha — площадь, га (для сценария area)
    """
    if scenario == "area":
        area_val = _f(fixed_area_ha, 0)
        s = _calc_one(silenta, 0)
        c = _calc_one(competitor, 0)

        cost_s = (s["seed_cost_per_ha"] + s["field_cost"]) * area_val
        cost_c = (c["seed_cost_per_ha"] + c["field_cost"]) * area_val
        saving_field = cost_c - cost_s

        dm_s = s["dm_yield"] * area_val
        dm_c = c["dm_yield"] * area_val
        dm_surplus_t = (dm_s - dm_c) / 10

        dm_pct_s = s["dm_pct"] / 100
        gm_surplus_t = dm_surplus_t / dm_pct_s if dm_pct_s > 0 else 0

        me_surplus_mj = dm_surplus_t * 1000 * s["me"]
        grain_equiv_t = me_surplus_mj / GRAIN_ME / 1000

        return {
            "scenario": "area",
            "silenta": s,
            "competitor": c,
            "same_area": area_val,
            "saving_field": saving_field,
            "cost_silenta": cost_s,
            "cost_competitor": cost_c,
            "surplus_dm_t": dm_surplus_t,
            "surplus_gm_t": gm_surplus_t,
            "surplus_me_mj": me_surplus_mj,
            "surplus_grain_t": grain_equiv_t,
        }
    else:  # herd
        silo_demand_c = _f(silo_demand_t, 0) * 10
        s = _calc_one(silenta, silo_demand_c)
        c = _calc_one(competitor, silo_demand_c)

        saving_field = c["total_cost"] - s["total_cost"]
        freed_area = c["area"] - s["area"]

        return {
            "scenario": "herd",
            "silenta": s,
            "competitor": c,
            "silo_demand_t": _f(silo_demand_t, 0),
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
