import pandas as pd

NORMS = {
    (650, 35): {"NEL": 220.0, "nXP": 3280, "DM": 24.0},
    (650, 30): {"NEL": 195.0, "nXP": 2900, "DM": 23.0},
    (650, 25): {"NEL": 170.0, "nXP": 2500, "DM": 22.0},
    (600, 30): {"NEL": 188.0, "nXP": 2800, "DM": 22.0},
    (600, 25): {"NEL": 165.0, "nXP": 2450, "DM": 21.0},
}

FEEDS_LIBRARY = {
    "сено злаково-бобовое": {"DM": 850, "NEL": 5.8, "nXP": 130, "NDF": 550},
    "сенаж люцерновый": {"DM": 450, "NEL": 6.5, "nXP": 150, "NDF": 450},
    "комбикорм": {"DM": 880, "NEL": 8.2, "nXP": 160, "NDF": 250},
    "защищённый жир": {"DM": 990, "NEL": 30.0, "nXP": 0, "NDF": 0},
    "премикс": {"DM": 950, "NEL": 0, "nXP": 0, "NDF": 0},
}

RATION_SHARES = {"силос": 0.45, "сено": 0.08, "сенаж": 0.12, "комбикорм": 0.33, "прочее": 0.02}

def get_norms(live_weight: float, milk_yield: float) -> dict:
    key = (int(live_weight), int(milk_yield))
    if key in NORMS: return NORMS[key]
    base = NORMS.get((650, 30), {"NEL": 195, "nXP": 2900, "DM": 23})
    delta = milk_yield - 30
    return {"NEL": base["NEL"] + delta * 5.0, "nXP": base["nXP"] + delta * 76.0, "DM": base["DM"] + delta * 0.2}

def calculate_ration(silo: dict, live_weight: float, milk_yield: float) -> dict:
    norms = get_norms(live_weight, milk_yield)
    total_dm = norms["DM"]
    silo_dm = total_dm * RATION_SHARES["силос"]
    silo_nel = silo_dm * (silo.get("NEL_VC") or silo.get("NEL"))
    silo_nxp = silo_dm * silo["nXP"]
    silo_ndf = silo_dm * silo["NDF"]
    ration = {"силос": {"dm": silo_dm, "nat": silo_dm / (silo["DM"] / 1000), "NEL": silo_nel, "nXP": silo_nxp, "NDF": silo_ndf}}
    remaining_dm = total_dm - silo_dm
    shares = {"сено": RATION_SHARES["сено"], "сенаж": RATION_SHARES["сенаж"], "комбикорм": RATION_SHARES["комбикорм"]}
    total_share = sum(shares.values())
    for feed, share in shares.items():
        f = FEEDS_LIBRARY[feed]
        dm = remaining_dm * (share / total_share)
        ration[feed] = {"dm": dm, "nat": dm / (f["DM"] / 1000), "NEL": dm * f["NEL"], "nXP": dm * f["nXP"], "NDF": dm * f["NDF"]}
    total = {"dm": sum(r["dm"] for r in ration.values()), "NEL": sum(r["NEL"] for r in ration.values()), "nXP": sum(r["nXP"] for r in ration.values()), "NDF": sum(r["NDF"] for r in ration.values())}
    deficit = {"NEL": norms["NEL"] - total["NEL"], "nXP": norms["nXP"] - total["nXP"]}
    corrections = []
    if deficit["NEL"] > 0:
        fat_needed = deficit["NEL"] / FEEDS_LIBRARY["защищённый жир"]["NEL"]
        corrections.append({"корм": "защищённый жир", "кг": round(fat_needed, 2), "NEL": round(fat_needed * FEEDS_LIBRARY["защищённый жир"]["NEL"], 1)})
        total["NEL"] += fat_needed * FEEDS_LIBRARY["защищённый жир"]["NEL"]
        total["dm"] += fat_needed * FEEDS_LIBRARY["защищённый жир"]["DM"] / 1000
    if deficit["nXP"] > 0:
        soy_dm = deficit["nXP"] / 220
        corrections.append({"корм": "соевый шрот (доп.)", "кг СВ": round(soy_dm, 2), "nXP": round(soy_dm * 220, 0)})
        total["nXP"] += soy_dm * 220
    return {"norms": norms, "ration": ration, "total": total, "deficit_before": deficit, "corrections": corrections}

def ration_to_dataframe(result: dict) -> pd.DataFrame:
    rows = []
    for feed, vals in result["ration"].items():
        rows.append({"Корм": feed, "СВ, кг": round(vals["dm"], 2), "Нат. вес, кг": round(vals["nat"], 2), "NEL, МДж": round(vals["NEL"], 1), "nXP, г": round(vals["nXP"], 0), "НДК, г": round(vals["NDF"], 0)})
    rows.append({"Корм": "ИТОГО", "СВ, кг": round(result["total"]["dm"], 2), "Нат. вес, кг": "", "NEL, МДж": round(result["total"]["NEL"], 1), "nXP, г": round(result["total"]["nXP"], 0), "НДК, г": round(result["total"]["NDF"], 0)})
    rows.append({"Корм": "НОРМА", "СВ, кг": result["norms"]["DM"], "Нат. вес, кг": "", "NEL, МДж": result["norms"]["NEL"], "nXP, г": result["norms"]["nXP"], "НДК, г": ""})
    return pd.DataFrame(rows)
