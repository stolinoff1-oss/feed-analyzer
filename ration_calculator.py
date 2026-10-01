import pandas as pd

NORMS = {
    (650, 35): {"NEL": 220.0, "nXP": 3280, "DM": 24.0},
    (650, 30): {"NEL": 195.0, "nXP": 2900, "DM": 23.0},
    (650, 25): {"NEL": 170.0, "nXP": 2500, "DM": 22.0},
    (600, 30): {"NEL": 188.0, "nXP": 2800, "DM": 22.0},
    (600, 25): {"NEL": 165.0, "nXP": 2450, "DM": 21.0},
}


# === СТАНДАРТНАЯ БИБЛИОТЕКА КОРМОВ (можно переопределить через sidebar) ===
DEFAULT_FEEDS_LIBRARY = {
    "сено":           {"DM": 850, "NEL": 5.8,  "nXP": 130, "NDF": 550},
    "сенаж":          {"DM": 450, "NEL": 6.5,  "nXP": 150, "NDF": 450},
    "комбикорм":      {"DM": 880, "NEL": 8.2,  "nXP": 160, "NDF": 250},
    "защищённый жир": {"DM": 990, "NEL": 30.0, "nXP": 0,   "NDF": 0},
    "соевый шрот":    {"DM": 900, "NEL": 8.0,  "nXP": 220, "NDF": 130},
}

# Старое имя для совместимости с другими файлами
FEEDS_LIBRARY = DEFAULT_FEEDS_LIBRARY

# Лимиты (по зоотехническим нормам)
HAY_PCT = 0.08
HAYLAGE_PCT = 0.10
SILO_MIN_PCT = 0.15
SILO_MAX_PCT = 0.50
CONC_MAX_PCT = 0.45
NDF_TARGET = 0.34
FAT_MAX_KG = 1.5
SOY_MAX_KG = 1.0


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


def get_norms(live_weight: float, milk_yield: float) -> dict:
    key = (int(live_weight), int(milk_yield))
    if key in NORMS:
        return NORMS[key]
    base = NORMS.get((650, 30), {"NEL": 195, "nXP": 2900, "DM": 23})
    delta = milk_yield - 30
    return {
        "NEL": base["NEL"] + delta * 5.0,
        "nXP": base["nXP"] + delta * 76.0,
        "DM":  base["DM"] + delta * 0.2,
    }


def _resolve_feeds(feeds_lib: dict = None) -> dict:
    """Возвращает итоговую библиотеку: DEFAULT + пользовательские override."""
    lib = {k: dict(v) for k, v in DEFAULT_FEEDS_LIBRARY.items()}
    if feeds_lib:
        for key, vals in feeds_lib.items():
            if key in lib and isinstance(vals, dict):
                for field, value in vals.items():
                    v = _f(value, None)
                    if v is not None:
                        lib[key][field] = v
    return lib


def _calc_adaptive(silo: dict, live_weight: float, milk_yield: float,
                   feeds_lib: dict) -> dict:
    """Адаптивный расчёт рациона по НДК-бюджету."""
    norms = get_norms(live_weight, milk_yield)
    total_dm = norms["DM"]

    silo_DM  = _f(silo.get("DM"), 365.0)
    silo_NEL = _f(silo.get("NEL_VC") or silo.get("NEL"), 7.0)
    silo_nXP = _f(silo.get("nXP"), 135.0)
    silo_NDF = _f(silo.get("NDF"), 350.0)
    silo_ndf_kg = silo_NDF / 1000.0

    # 1. Структурные корма
    hay_dm     = total_dm * HAY_PCT
    haylage_dm = total_dm * HAYLAGE_PCT

    ndf_hay_kg     = hay_dm     * feeds_lib["сено"]["NDF"]  / 1000.0
    ndf_haylage_kg = haylage_dm * feeds_lib["сенаж"]["NDF"] / 1000.0

    # 2. Бюджет НДК
    ndf_max = total_dm * NDF_TARGET
    ndf_avail = ndf_max - ndf_hay_kg - ndf_haylage_kg
    remaining_dm = total_dm - hay_dm - haylage_dm

    # 3. Силос
    conc_ndf_kg = feeds_lib["комбикорм"]["NDF"] / 1000.0
    if silo_ndf_kg > conc_ndf_kg:
        denom = silo_ndf_kg - conc_ndf_kg
        s_max = (ndf_avail - remaining_dm * conc_ndf_kg) / denom
    else:
        s_max = remaining_dm

    silo_min = total_dm * SILO_MIN_PCT
    silo_max = min(s_max, total_dm * SILO_MAX_PCT)
    silo_max = max(silo_max, silo_min)

    silo_dm = max(min(silo_max, remaining_dm), silo_min)
    conc_dm = remaining_dm - silo_dm

    # 4. Ограничение комбикорма
    max_conc = total_dm * CONC_MAX_PCT
    if conc_dm > max_conc:
        hay_dm += (conc_dm - max_conc)
        conc_dm = max_conc

    # 5. Энергия и протеин
    nel_silo    = silo_dm    * silo_NEL
    nel_hay     = hay_dm     * feeds_lib["сено"]["NEL"]
    nel_haylage = haylage_dm * feeds_lib["сенаж"]["NEL"]
    nel_conc    = conc_dm    * feeds_lib["комбикорм"]["NEL"]

    nxp_silo    = silo_dm    * silo_nXP
    nxp_hay     = hay_dm     * feeds_lib["сено"]["nXP"]
    nxp_haylage = haylage_dm * feeds_lib["сенаж"]["nXP"]
    nxp_conc    = conc_dm    * feeds_lib["комбикорм"]["nXP"]

    ndf_silo_val    = silo_dm    * silo_ndf_kg
    ndf_hay_val     = hay_dm     * feeds_lib["сено"]["NDF"]    / 1000.0
    ndf_haylage_val = haylage_dm * feeds_lib["сенаж"]["NDF"]   / 1000.0
    ndf_conc_val    = conc_dm    * conc_ndf_kg

    # 6. Жир — замена комбикорма
    fat_kg = 0.0
    nel_total = nel_silo + nel_hay + nel_haylage + nel_conc
    deficit_nel = norms["NEL"] - nel_total
    if deficit_nel > 0:
        diff = (feeds_lib["защищённый жир"]["NEL"]
                - feeds_lib["комбикорм"]["NEL"])
        if diff > 0:
            fat_kg = deficit_nel / diff
            fat_kg = min(fat_kg, conc_dm * 0.6, FAT_MAX_KG)
            conc_dm -= fat_kg
            nel_conc    -= fat_kg * feeds_lib["комбикорм"]["NEL"]
            nxp_conc    -= fat_kg * feeds_lib["комбикорм"]["nXP"]
            ndf_conc_val -= fat_kg * conc_ndf_kg

    # 7. Соевый шрот — замена комбикорма
    soy_dm = 0.0
    nxp_total = nxp_silo + nxp_hay + nxp_haylage + nxp_conc
    deficit_nxp = norms["nXP"] - nxp_total
    if deficit_nxp > 0:
        diff_nxp = (feeds_lib["соевый шрот"]["nXP"]
                    - feeds_lib["комбикорм"]["nXP"])
        if diff_nxp > 0:
            soy_dm = deficit_nxp / diff_nxp
            soy_dm = min(soy_dm, conc_dm * 0.5, SOY_MAX_KG)
            conc_dm -= soy_dm
            nxp_conc    -= soy_dm * feeds_lib["комбикорм"]["nXP"]
            nel_conc    -= soy_dm * feeds_lib["комбикорм"]["NEL"]
            ndf_conc_val -= soy_dm * conc_ndf_kg

    # 8. Итог
    silo_nat = silo_dm / (silo_DM / 1000.0) if silo_DM else 0
    hay_nat  = hay_dm / (feeds_lib["сено"]["DM"] / 1000.0)
    haylage_nat = haylage_dm / (feeds_lib["сенаж"]["DM"] / 1000.0)
    conc_nat = conc_dm / (feeds_lib["комбикорм"]["DM"] / 1000.0)
    fat_nat  = fat_kg
    soy_nat  = soy_dm / (feeds_lib["соевый шрот"]["DM"] / 1000.0)

    total_ndf = (ndf_silo_val + ndf_hay_val + ndf_haylage_val
                 + ndf_conc_val
                 + soy_dm * feeds_lib["соевый шрот"]["NDF"] / 1000.0)
    total_nel = (nel_silo + nel_hay + nel_haylage + nel_conc
                 + fat_kg * feeds_lib["защищённый жир"]["NEL"]
                 + soy_dm * feeds_lib["соевый шрот"]["NEL"])
    total_nxp = (nxp_silo + nxp_hay + nxp_haylage + nxp_conc
                 + soy_dm * feeds_lib["соевый шрот"]["nXP"])
    total_dm_actual = (silo_dm + hay_dm + haylage_dm + conc_dm
                       + fat_kg * feeds_lib["защищённый жир"]["DM"] / 1000.0
                       + soy_dm)

    ration = {
        "силос":    {"dm": silo_dm, "nat": silo_nat,
                     "NEL": nel_silo, "nXP": nxp_silo, "NDF": ndf_silo_val},
        "сено":     {"dm": hay_dm, "nat": hay_nat,
                     "NEL": nel_hay, "nXP": nxp_hay, "NDF": ndf_hay_val},
        "сенаж":    {"dm": haylage_dm, "nat": haylage_nat,
                     "NEL": nel_haylage, "nXP": nxp_haylage,
                     "NDF": ndf_haylage_val},
        "комбикорм": {"dm": conc_dm, "nat": conc_nat,
                      "NEL": nel_conc, "nXP": nxp_conc, "NDF": ndf_conc_val},
    }
    if fat_kg > 0:
        f = feeds_lib["защищённый жир"]
        ration["защищённый жир"] = {
            "dm": fat_kg * f["DM"] / 1000.0, "nat": fat_nat,
            "NEL": fat_kg * f["NEL"], "nXP": 0, "NDF": 0,
        }
    if soy_dm > 0:
        f = feeds_lib["соевый шрот"]
        ration["соевый шрот"] = {
            "dm": soy_dm, "nat": soy_nat,
            "NEL": soy_dm * f["NEL"], "nXP": soy_dm * f["nXP"],
            "NDF": soy_dm * f["NDF"] / 1000.0,
        }

    # 9. Предупреждения
    warnings = []
    if total_nel < norms["NEL"] * 0.95:
        warnings.append(
            f"⚠️ NEL не достигает нормы: {total_nel:.0f} из {norms['NEL']} МДж."
        )
    ndf_pct = 100 * total_ndf / total_dm_actual if total_dm_actual else 0
    if ndf_pct > 36:
        warnings.append(
            f"⚠️ НДК в рационе = {ndf_pct:.1f}% (норма 32–34%)."
        )
    if fat_kg >= FAT_MAX_KG * 0.95 and deficit_nel > 0:
        warnings.append(f"⚠️ Жир на максимуме ({fat_kg:.2f} кг).")
    if total_dm_actual and conc_dm / total_dm_actual >= 0.44:
        warnings.append(
            f"⚠️ Концентраты = {100*conc_dm/total_dm_actual:.0f}%. "
            "Добавьте буферы (сода 150 г/сут)."
        )

    composition = {
        "silo_pct": 100 * silo_dm / total_dm_actual if total_dm_actual else 0,
        "hay_pct": 100 * hay_dm / total_dm_actual if total_dm_actual else 0,
        "haylage_pct": 100 * haylage_dm / total_dm_actual if total_dm_actual else 0,
        "conc_pct": 100 * conc_dm / total_dm_actual if total_dm_actual else 0,
        "fat_kg": fat_kg,
        "soy_dm": soy_dm,
        "ndf_pct": ndf_pct,
        "silo_dm": silo_dm,
        "hay_dm": hay_dm,
        "haylage_dm": haylage_dm,
        "concentrate_dm": conc_dm,
    }

    return {
        "norms": norms,
        "ration": ration,
        "total": {"dm": total_dm_actual, "NEL": total_nel,
                  "nXP": total_nxp, "NDF": total_ndf},
        "deficit_before": {"NEL": norms["NEL"] - total_nel,
                            "nXP": norms["nXP"] - total_nxp},
        "corrections": _make_corrections(fat_kg, soy_dm, feeds_lib),
        "composition": composition,
        "warnings": warnings,
    }


def _make_corrections(fat_kg: float, soy_dm: float, feeds_lib: dict) -> list:
    corrections = []
    if fat_kg > 0:
        f = feeds_lib["защищённый жир"]
        corrections.append({
            "корм": "защищённый жир",
            "кг": round(fat_kg, 2),
            "NEL": round(fat_kg * f["NEL"], 1),
        })
    if soy_dm > 0:
        f = feeds_lib["соевый шрот"]
        corrections.append({
            "корм": "соевый шрот",
            "кг СВ": round(soy_dm, 2),
            "nXP": round(soy_dm * f["nXP"], 0),
        })
    return corrections


def _calc_custom(silo: dict, live_weight: float, milk_yield: float,
                 custom: dict, feeds_lib: dict) -> dict:
    """Режим ручного редактирования — состав задан пользователем."""
    norms = get_norms(live_weight, milk_yield)

    silo_DM  = _f(silo.get("DM"), 365.0)
    silo_NEL = _f(silo.get("NEL_VC") or silo.get("NEL"), 7.0)
    silo_nXP = _f(silo.get("nXP"), 135.0)
    silo_NDF = _f(silo.get("NDF"), 350.0)

    comp = {
        "silo_dm":        _f(custom.get("silo_dm"), 0.0),
        "hay_dm":         _f(custom.get("hay_dm"), 0.0),
        "haylage_dm":     _f(custom.get("haylage_dm"), 0.0),
        "concentrate_dm": _f(custom.get("concentrate_dm"), 0.0),
        "fat_kg":         _f(custom.get("fat_kg"), 0.0),
        "soy_dm":         _f(custom.get("soy_dm"), 0.0),
    }

    ration = {}
    if comp["silo_dm"] > 0:
        ration["силос"] = {
            "dm": comp["silo_dm"],
            "nat": comp["silo_dm"] / (silo_DM / 1000.0) if silo_DM else 0,
            "NEL": comp["silo_dm"] * silo_NEL,
            "nXP": comp["silo_dm"] * silo_nXP,
            "NDF": comp["silo_dm"] * silo_NDF / 1000.0,
        }
    for key, dm in [("сено", comp["hay_dm"]),
                    ("сенаж", comp["haylage_dm"]),
                    ("комбикорм", comp["concentrate_dm"])]:
        if dm <= 0:
            continue
        f = feeds_lib[key]
        ration[key] = {
            "dm": dm, "nat": dm / (f["DM"] / 1000.0),
            "NEL": dm * f["NEL"], "nXP": dm * f["nXP"],
            "NDF": dm * f["NDF"] / 1000.0,
        }
    if comp["fat_kg"] > 0:
        f = feeds_lib["защищённый жир"]
        dm_fat = comp["fat_kg"] * f["DM"] / 1000.0
        ration["защищённый жир"] = {
            "dm": dm_fat, "nat": comp["fat_kg"],
            "NEL": dm_fat * f["NEL"], "nXP": 0, "NDF": 0,
        }
    if comp["soy_dm"] > 0:
        f = feeds_lib["соевый шрот"]
        ration["соевый шрот"] = {
            "dm": comp["soy_dm"], "nat": comp["soy_dm"] / (f["DM"] / 1000.0),
            "NEL": comp["soy_dm"] * f["NEL"],
            "nXP": comp["soy_dm"] * f["nXP"],
            "NDF": comp["soy_dm"] * f["NDF"] / 1000.0,
        }

    total = {
        "dm":  sum(r["dm"]  for r in ration.values()),
        "NEL": sum(r["NEL"] for r in ration.values()),
        "nXP": sum(r["nXP"] for r in ration.values()),
        "NDF": sum(r["NDF"] for r in ration.values()),
    }

    warnings = []
    ndf_pct = 100 * total["NDF"] / total["dm"] if total["dm"] else 0
    if ndf_pct > 36:
        warnings.append(f"⚠️ НДК = {ndf_pct:.1f}% (норма ≤34%).")
    if total["dm"] and comp["concentrate_dm"] / total["dm"] > 0.45:
        warnings.append("⚠️ Концентраты > 45% СВ — риск ацидоза.")

    return {
        "norms": norms,
        "ration": ration,
        "total": total,
        "deficit_before": {"NEL": norms["NEL"] - total["NEL"],
                            "nXP": norms["nXP"] - total["nXP"]},
        "corrections": [],
        "composition": {
            **comp,
            "silo_pct": 100 * comp["silo_dm"] / total["dm"] if total["dm"] else 0,
            "conc_pct": 100 * comp["concentrate_dm"] / total["dm"] if total["dm"] else 0,
            "ndf_pct": ndf_pct,
        },
        "warnings": warnings,
    }


def calculate_ration(silo: dict, live_weight: float, milk_yield: float,
                     custom: dict = None, feeds_lib: dict = None) -> dict:
    """
    feeds_lib — опциональный словарь с переопределениями кормов.
    Формат: {"сено": {"NEL": 6.5, "nXP": 130}, "сенаж": {...}, ...}
    """
    resolved = _resolve_feeds(feeds_lib)
    if custom is not None:
        return _calc_custom(silo, live_weight, milk_yield, custom, resolved)
    return _calc_adaptive(silo, live_weight, milk_yield, resolved)


def ration_to_dataframe(result: dict) -> pd.DataFrame:
    rows = []
    for feed, vals in result["ration"].items():
        rows.append({
            "Корм": feed,
            "СВ, кг": round(vals["dm"], 2),
            "Нат. вес, кг": round(vals["nat"], 2),
            "NEL, МДж": round(vals["NEL"], 1),
            "nXP, г": round(vals["nXP"], 0),
            "НДК, г": round(vals["NDF"] * 1000, 0),
            "% СВ": (round(100 * vals["dm"] / result["total"]["dm"], 1)
                     if result["total"]["dm"] else 0),
        })
    rows.append({
        "Корм": "ИТОГО",
        "СВ, кг": round(result["total"]["dm"], 2),
        "Нат. вес, кг": "",
        "NEL, МДж": round(result["total"]["NEL"], 1),
        "nXP, г": round(result["total"]["nXP"], 0),
        "НДК, г": round(result["total"]["NDF"] * 1000, 0),
        "% СВ": 100.0,
    })
    rows.append({
        "Корм": "НОРМА",
        "СВ, кг": result["norms"]["DM"],
        "Нат. вес, кг": "",
        "NEL, МДж": result["norms"]["NEL"],
        "nXP, г": result["norms"]["nXP"],
        "НДК, г": "",
        "% СВ": "",
    })
    return pd.DataFrame(rows)
