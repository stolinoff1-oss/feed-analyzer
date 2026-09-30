import pandas as pd

COLUMNS = {
    "sample_id": "Номер образца", "feed_name": "Наименование корма", "location": "Местонахождения",
    "DM": "Сухая масса, (г/кг) (DM)", "CP": "Сырой протеин (г/кг СВ) (Crude protein)",
    "starch": "Крахмал (г/кг СВ) (Starch)", "sugar": "Сахар (г/кг СВ) (Sugar)",
    "NDF": "Нейтрально-детергентная клетчатка (НДК) (г/кг СВ) (NDF)",
    "ADF": "Кислотно-детергентная клетчатка (КДК) (г/кг СВ) (ADF)",
    "ADL": "Кислотно-детергентный лингнин (КДЛ) (г/кг СВ) (ADL)",
    "NDFd": "НДК-перевариваемость (%) (NDF digest.)", "dOM": "Переваримость ОВ (%) (Dig.OM)",
    "NEL": "Чистая энергия лактации (МДж/кг СВ) (NEL)",
    "NEL_VC": "Чистая энергия лактации с учетом переваримости ОВ (МДж/кг СВ) (NEL-VC)",
    "ME": "Обменная энергия (МДж/кг СВ) (ME)", "nXP": "Усвоенный протеин (г/кг СВ) (nXP)",
    "UDP": "Нерасщепляемый в рубце протеин (г/кг СВ) (UDP)",
    "RNB": "Баланс азота в рубце (г/кг СВ) (RNB)", "structure": "Структурный показатель (Structure value)",
    "NFC": "Неструктурные углеводы (г/кг СВ) (NFC)", "ash": "Сырая зола (г/кг СВ) (Crude ash)",
    "fat": "Сырой жир (г/кг СВ) (Crude fat)", "CF": "Сырая клетчатка (г/кг СВ) (Crude fibre)",
    "Cl": "Хлорид (г/кг СВ) (Clorine)",
}

def load_feed_data(path: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="Результаты анализа", header=0)
    rename_map = {v: k for k, v in COLUMNS.items()}
    df = df.rename(columns=rename_map)
    keep = [c for c in COLUMNS.keys() if c in df.columns]
    df = df[keep].copy()
    for col in df.columns:
        if col not in ("sample_id", "feed_name", "location"):
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["sample_id"]).reset_index(drop=True)

def analyze_feeds(df: pd.DataFrame) -> dict:
    result = {"samples": [], "leaders": {}, "ratings": []}
    for _, row in df.iterrows():
        sample = {k: row.get(k) for k in ["sample_id", "feed_name", "location", "DM", "CP", "starch", "sugar", "NDF", "ADF", "NDFd", "dOM", "NEL", "NEL_VC", "nXP", "RNB", "structure"]}
        sample["name"] = sample.get("location") or sample.get("feed_name")
        sample["id"] = sample.get("sample_id")
        result["samples"].append(sample)

    def _leader(col, higher_better=True):
        valid = [s for s in result["samples"] if s.get(col) is not None and not pd.isna(s.get(col))]
        if not valid: return None
        return (max if higher_better else min)(valid, key=lambda s: s[col])

    result["leaders"] = {
        "max_CP": _leader("CP", True), "max_starch": _leader("starch", True),
        "max_sugar": _leader("sugar", True), "min_NDF": _leader("NDF", False),
        "max_dOM": _leader("dOM", True), "max_NEL_VC": _leader("NEL_VC", True),
        "best_RNB": _leader("RNB", True),
    }

    for s in result["samples"]:
        score = 0
        if s["NEL_VC"]: score += (s["NEL_VC"] - 6.5) * 30
        if s["CP"]: score += (s["CP"] - 60) * 1.0
        if s["starch"]: score += (s["starch"] - 250) * 0.1
        if s["NDF"]: score -= (s["NDF"] - 300) * 0.05
        if s["dOM"]: score += (s["dOM"] - 75) * 1.5
        if s["RNB"]: score -= abs(s["RNB"] + 8) * 2
        s["score"] = round(score, 2)

    result["ratings"] = sorted(result["samples"], key=lambda s: s["score"], reverse=True)
    return result

def feeds_to_dataframe(result: dict) -> pd.DataFrame:
    rows = []
    for i, s in enumerate(result["ratings"], 1):
        rows.append({"Рейтинг": i, "Образец": s["name"], "Номер": s["id"], "СП, г/кг": s["CP"], "Крахмал": s["starch"], "Сахар": s["sugar"], "НДК": s["NDF"], "КДК": s["ADF"], "Перев. ОВ, %": s["dOM"], "NEL": s["NEL"], "NEL-VC": s["NEL_VC"], "nXP": s["nXP"], "RNB": s["RNB"], "Балл": s["score"]})
    return pd.DataFrame(rows)
