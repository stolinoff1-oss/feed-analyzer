import pandas as pd
import numpy as np
import re


def _num(x):
    if x is None:
        return None
    try:
        f = float(x)
        if np.isnan(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _normalize(s: str) -> str:
    """Убирает все виды пробелов и переводит в нижний регистр."""
    s = str(s)
    s = s.replace("\xa0", " ").replace("\u2009", " ").replace("\u202f", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


# Шаблоны: короткое имя → список подстрок (в нижнем регистре), по которым ищем колонку
PATTERNS = {
    "sample_id": ["номер образца"],
    "feed_name": ["наименование корма"],
    "location":  ["местонахождения"],
    "DM":        ["сухая масса"],
    "starch":    ["крахмал"],
    "sugar":     ["сахар"],
    "NDF":       ["нейтрально-детергентная клетчатка"],
    "ADF":       ["кислотно-детергентная клетчатка"],
    "ADL":       ["кислотно-детергентный лингнин"],
    "NDFd":      ["ндк-перевариваемость", "ndf digest"],
    "dOM":       ["переваримость ов"],
    "NEL_VC":    ["nel-vc"],
    "NEL":       ["чистая энергия лактации"],
    "nXP":       ["(nxp)"],
    "UDP":       ["(udp)"],
    "RNB":       ["(rnb)"],
    "structure": ["structure value"],
    "NFC":       ["(nfc)"],
    "ash":       ["сырая зола"],
    "fat":       ["сырой жир"],
    "CF":        ["сырая клетчатка"],
    "Cl":        ["хлорид"],
}


def _find_cp_column(columns):
    """Ищет колонку 'сырой протеин' НЕ total. Возвращает имя колонки или None."""
    for col in columns:
        c = _normalize(col)
        if "protein" in c and "total" not in c and "общий" not in c:
            return col
    for col in columns:
        c = _normalize(col)
        if "сырой протеин" in c and "общий" not in c:
            return col
    return None


def load_feed_data(path: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="Результаты анализа", header=0)

    # Сопоставление колонок
    rename_map = {}
    used = set()

    for short, keywords in PATTERNS.items():
        for col in df.columns:
            if col in used:
                continue
            c = _normalize(col)
            if any(kw in c for kw in keywords):
                # NEL (не NEL-VC)
                if short == "NEL" and "nel-vc" in c:
                    continue
                rename_map[col] = short
                used.add(col)
                break

    # Отдельно ищем CP, чтобы не захватить "Total Crude protein"
    cp_col = _find_cp_column([c for c in df.columns if c not in used])
    if cp_col:
        rename_map[cp_col] = "CP"
        used.add(cp_col)

    df = df.rename(columns=rename_map)

    # Оставляем только известные колонки
    keep = [c for c in PATTERNS.keys()] + ["CP"]
    keep = [c for c in keep if c in df.columns]
    df = df[keep].copy()

    # Преобразуем в числа
    for col in df.columns:
        if col not in ("sample_id", "feed_name", "location"):
            df[col] = pd.to_numeric(df[col], errors="coerce")

    return df.dropna(subset=["sample_id"]).reset_index(drop=True)


def analyze_feeds(df: pd.DataFrame) -> dict:
    result = {"samples": [], "leaders": {}, "ratings": []}
    numeric_keys = ["DM", "CP", "starch", "sugar", "NDF", "ADF", "NDFd", "dOM",
                    "NEL", "NEL_VC", "nXP", "RNB", "structure"]

    for _, row in df.iterrows():
        sample = {"id": row.get("sample_id"),
                  "name": row.get("location") or row.get("feed_name")}
        for k in numeric_keys:
            sample[k] = _num(row.get(k))
        result["samples"].append(sample)

    def _leader(col, higher_better=True):
        valid = [s for s in result["samples"] if s.get(col) is not None]
        if not valid:
            return None
        return (max if higher_better else min)(valid, key=lambda s: s[col])

    result["leaders"] = {
        "max_CP":     _leader("CP", True),
        "max_starch": _leader("starch", True),
        "max_sugar":  _leader("sugar", True),
        "min_NDF":    _leader("NDF", False),
        "max_dOM":    _leader("dOM", True),
        "max_NEL_VC": _leader("NEL_VC", True),
        "best_RNB":   _leader("RNB", True),
    }

    for s in result["samples"]:
        score = 0.0
        if s["NEL_VC"] is not None: score += (s["NEL_VC"] - 6.5) * 30
        if s["CP"]     is not None: score += (s["CP"] - 60) * 1.0
        if s["starch"] is not None: score += (s["starch"] - 250) * 0.1
        if s["NDF"]    is not None: score -= (s["NDF"] - 300) * 0.05
        if s["dOM"]    is not None: score += (s["dOM"] - 75) * 1.5
        if s["RNB"]    is not None: score -= abs(s["RNB"] + 8) * 2
        s["score"] = round(score, 2)

    result["ratings"] = sorted(result["samples"], key=lambda s: s["score"], reverse=True)
    return result


def feeds_to_dataframe(result: dict) -> pd.DataFrame:
    rows = []
    for i, s in enumerate(result["ratings"], 1):
        rows.append({
            "Рейтинг": i, "Образец": s["name"], "Номер": s["id"],
            "DM": s["DM"], "СП, г/кг": s["CP"], "Крахмал": s["starch"],
            "Сахар": s["sugar"], "НДК": s["NDF"], "КДК": s["ADF"],
            "Перев. ОВ, %": s["dOM"], "NEL": s["NEL"], "NEL-VC": s["NEL_VC"],
            "nXP": s["nXP"], "RNB": s["RNB"], "Балл": s["score"],
        })
    return pd.DataFrame(rows)
