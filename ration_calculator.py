import pandas as pd

NORMS = {
    (650, 35): {"NEL": 220.0, "nXP": 3280, "DM": 24.0},
    (650, 30): {"NEL": 195.0, "nXP": 2900, "DM": 23.0},
    (650, 25): {"NEL": 170.0, "nXP": 2500, "DM": 22.0},
    (600, 30): {"NEL": 188.0, "nXP": 2800, "DM": 22.0},
    (600, 25): {"NEL": 165.0, "nXP": 2450, "DM": 21.0},
}

FEEDS_LIBRARY = {
    "сено":           {"DM": 850, "NEL": 5.8,  "nXP": 130, "NDF": 550},
    "сенаж":          {"DM": 450, "NEL": 6.5,  "nXP": 150, "NDF": 450},
    "комбикорм":      {"DM": 880, "NEL": 8.2,  "nXP": 160, "NDF": 250},
    "защищённый жир": {"DM": 990, "NEL": 30.0, "nXP": 0,   "NDF": 0},
    "соевый шрот":    {"DM": 900, "NEL": 8.0,  "nXP": 220, "NDF": 130},
    "премикс":        {"DM": 950, "NEL": 0,    "nXP": 0,   "NDF": 0},
}

RATION_SHARES = {"силос": 0.45, "сено": 0.08,
                 "сенаж": 0.12, "комбикорм": 0.33}


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


def _default_composition(total_dm: float) -> dict:
    """Дефолтный состав рациона (в кг СВ)."""
    silo_dm = total_dm * RATION_SHARES["силос"]
    remaining = total_dm - silo_dm
    shares = {"сено": RATION_SHARES["сено"],
              "сенаж": RATION_SHARES["сенаж"],
              "комбикорм": RATION_SHARES["комбикорм"]}
    total_share = sum(shares.values())
    return {
        "silo_dm":        silo_dm,
        "hay_dm":         remaining * (shares["сено"] / total_share),
        "haylage_dm":     remaining * (shares["сенаж"] / total_share),
        "concentrate_dm": remaining * (shares["комбикорм"] / total_share),
        "fat_kg":         0.0,
        "soy_dm":         0.0,
    }


def calculate_ration(silo: dict, live_weight: float, milk_yield: float,
                     custom: dict = None) -> dict:
    """
    silo: dict с полями DM, NEL/NEL_VC, nXP, NDF
    custom: словарь с составом рациона (silo_dm, hay_dm, haylage_dm,
        concentrate_dm, fat_kg, soy_dm). Если None — используется дефолтный
        состав и автоподбор жира/шрота до нормы.
    """
    norms = get_norms(live_weight, milk_yield)
    total_dm = norms["DM"]

    if custom is None:
        comp = _default_composition(total_dm)
        auto_correct = True
    else:
        comp = {
            "silo_dm":        _f(custom.get("silo_dm"), 0.0),
            "hay_dm":         _f(custom.get("hay_dm"), 0.0),
            "haylage_dm":     _f(custom.get("haylage_dm"), 0.0),
            "concentrate_dm": _f(custom.get("concentrate_dm"), 0.0),
            "fat_kg":         _f(custom.get("fat_kg"), 0.0),
            "soy_dm":         _f(custom.get("soy_dm"), 0.0),
        }
        auto_correct = False

    # --- Силос ---
    silo_DM  = _f(silo.get("DM"), 350.0)
    silo_NEL = _f(silo.get("NEL_VC") or silo.get("NEL"), 7.0)
    silo_nXP = _f(silo.get("nXP"), 135.0)
    silo_NDF = _f(silo.get("NDF"), 350.0)

    ration = {}
    if comp["silo_dm"] > 0:
        ration["силос"] = {
            "dm":  comp["silo_dm"],
            "nat": comp["silo_dm"] / (silo_DM / 1000) if silo_DM else 0,
            "NEL": comp["silo_dm"] * silo_NEL,
            "nXP": comp["silo_dm"] * silo_nXP,
            "NDF": comp["silo_dm"] * silo_NDF,
        }

    # --- Стандартные корма ---
    for key, dm in [("сено", comp["hay_dm"]),
                    ("сенаж", comp["haylage_dm"]),
                    ("комбикорм", comp["concentrate_dm"])]:
        if dm <= 0:
            continue
        f = FEEDS_LIBRARY[key]
        ration[key] = {
            "dm":  dm,
            "nat": dm / (f["DM"] / 1000),
            "NEL": dm * f["NEL"],
            "nXP": dm * f["nXP"],
            "NDF": dm * f["NDF"],
        }

    # --- Дополнительные корма ---
    if comp["fat_kg"] > 0:
        f = FEEDS_LIBRARY["защищённый жир"]
        dm_fat = comp["fat_kg"] * f["DM"] / 1000
        ration["защищённый жир"] = {
            "dm": dm_fat, "nat": comp["fat_kg"],
            "NEL": dm_fat * f["NEL"], "nXP": 0, "NDF": 0,
        }
    if comp["soy_dm"] > 0:
        f = FEEDS_LIBRARY["соевый шрот"]
        ration["соевый шрот"] = {
            "dm":  comp["soy_dm"],
            "nat": comp["soy_dm"] / (f["DM"] / 1000),
            "NEL": comp["soy_dm"] * f["NEL"],
            "nXP": comp["soy_dm"] * f["nXP"],
            "NDF": comp["soy_dm"] * f["NDF"],
        }

    # --- Итог ---
    def _sum(key):
        return sum(r[key] for r in ration.values()) if ration else 0.0

    total = {"dm": _sum("dm"), "NEL": _sum("NEL"),
             "nXP": _sum("nXP"), "NDF": _sum("NDF")}

    deficit = {"NEL": norms["NEL"] - total["NEL"],
               "nXP": norms["nXP"] - total["nXP"]}

    corrections = []

    # Автоподбор только если custom не задан
    if auto_correct:
        if deficit["NEL"] > 0:
            f = FEEDS_LIBRARY["защищённый жир"]
            fat_needed = deficit["NEL"] / f["NEL"]
            corrections.append({
                "корм": "защищённый жир",
                "кг": round(fat_needed, 2),
                "NEL": round(fat_needed * f["NEL"], 1),
            })
            dm_fat = fat_needed * f["DM"] / 1000
            if "защищённый жир" in ration:
                ration["защищённый жир"]["dm"]  += dm_fat
                ration["защищённый жир"]["nat"] += fat_needed
                ration["защищённый жир"]["NEL"] += dm_fat * f["NEL"]
            else:
                ration["защищённый жир"] = {
                    "dm": dm_fat, "nat": fat_needed,
                    "NEL": dm_fat * f["NEL"], "nXP": 0, "NDF": 0,
                }
            total["NEL"] += dm_fat * f["NEL"]
            total["dm"]  += dm_fat

        if deficit["nXP"] > 0:
            f = FEEDS_LIBRARY["соевый шрот"]
            soy_kg = deficit["nXP"] / f["nXP"]
            corrections.append({
                "корм": "соевый шрот (доп.)",
                "кг СВ": round(soy_kg, 2),
                "nXP": round(soy_kg * f["nXP"], 0),
            })
            if "соевый шрот" in ration:
                ration["соевый шрот"]["dm"]  += soy_kg
                ration["соевый шрот"]["nat"] += soy_kg / (f["DM"] / 1000)
                ration["соевый шрот"]["NEL"] += soy_kg * f["NEL"]
                ration["соевый шрот"]["nXP"] += soy_kg * f["nXP"]
                ration["соевый шрот"]["NDF"] += soy_kg * f["NDF"]
            else:
                ration["соевый шрот"] = {
                    "dm":  soy_kg,
                    "nat": soy_kg / (f["DM"] / 1000),
                    "NEL": soy_kg * f["NEL"],
                    "nXP": soy_kg * f["nXP"],
                    "NDF": soy_kg * f["NDF"],
                }
            total["nXP"] += soy_kg * f["nXP"]
            total["NEL"] += soy_kg * f["NEL"]
            total["NDF"] += soy_kg * f["NDF"]
            total["dm"]  += soy_kg

    return {
        "norms": norms,
        "ration": ration,
        "total": total,
        "deficit_before": deficit,
        "corrections": corrections,
        "composition": comp,
    }


def ration_to_dataframe(result: dict) -> pd.DataFrame:
    rows = []
    for feed, vals in result["ration"].items():
        rows.append({
            "Корм": feed,
            "СВ, кг": round(vals["dm"], 2),
            "Нат. вес, кг": round(vals["nat"], 2),
            "NEL, МДж": round(vals["NEL"], 1),
            "nXP, г": round(vals["nXP"], 0),
            "НДК, г": round(vals["NDF"], 0),
        })
    rows.append({
        "Корм": "ИТОГО",
        "СВ, кг": round(result["total"]["dm"], 2),
        "Нат. вес, кг": "",
        "NEL, МДж": round(result["total"]["NEL"], 1),
        "nXP, г": round(result["total"]["nXP"], 0),
        "НДК, г": round(result["total"]["NDF"], 0),
    })
    rows.append({
        "Корм": "НОРМА",
        "СВ, кг": result["norms"]["DM"],
        "Нат. вес, кг": "",
        "NEL, МДж": result["norms"]["NEL"],
        "nXP, г": result["norms"]["nXP"],
        "НДК, г": "",
    })
    return pd.DataFrame(rows)
