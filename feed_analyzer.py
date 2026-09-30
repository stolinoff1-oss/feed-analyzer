import pandas as pd
import numpy as np
import re


def _num(x):
    if x is None:
        return None
    if isinstance(x, str):
        x = re.sub(r"[\s\xa0\u200b\u2060]+", "", x).replace(",", ".")
        if not x:
            return None
    try:
        f = float(x)
        if np.isnan(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _normalize(s: str) -> str:
    s = str(s)
    s = re.sub(r"[\ufeff\u200b-\u200f\u2060-\u206f]", "", s)
    s = s.replace("\xa0", " ").replace("\u2009", " ").replace("\u202f", " ")
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


# СП полностью убран из анализа
FIND_SPECS = [
    ("sample_id", ["номер образца"], []),
    ("feed_name", ["наименование корма"], []),
    ("location",  ["местонахождения"], []),
    ("DM",        ["сухая масса"], []),
    ("starch",    ["крахмал", "starch"], ["bypass", "транзит"]),
    ("sugar",     ["сахар", "sugar"], []),
    ("NDF",       ["нейтрально-детергентная клетчатка", "ndf"],
                  ["перевар", "digest"]),
    ("ADF",       ["кислотно-детергентная клетчатка", "adf"], []),
    ("ADL",       ["кислотно-детергентный лингнин", "adl"], []),
    ("NDFd",      ["ндк-перевариваемость", "ndf digest"], []),
    ("dOM",       ["переваримость ов"], []),
    ("NEL_VC",    ["nel-vc"], []),
    ("NEL",       ["чистая энергия лактации"], ["nel-vc"]),
    ("nXP",       ["(nxp)", " nxp"], []),
    ("UDP",       ["(udp)", " udp"], []),
    ("RNB",       ["(rnb)", " rnb"], []),
    ("structure", ["structure value"], []),
    ("NFC",       ["(nfc)"], []),
    ("ash",       ["сырая зола", "crude ash"], []),
    ("fat",       ["сырой жир", "crude fat"], []),
    ("CF",        ["сырая клетчатка", "crude fibre", "crude fiber"], []),
    ("Cl",        ["хлорид", "chlorine", "clorine"], []),
]


def load_feed_data(path: str) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="Результаты анализа", header=0)
    df.columns = [re.sub(r"[\ufeff\u200b-\u200f\u2060-\u206f]", "",
                          str(c)).strip() for c in df.columns]

    rename_map = {}
    used = set()
    for short, keywords, excludes in FIND_SPECS:
        for col in df.columns:
            if col in used:
                continue
            c = _normalize(col)
            if any(kw in c for kw in keywords):
                if any(ex in c for ex in excludes):
                    continue
                rename_map[col] = short
                used.add(col)
                break

    df = df.rename(columns=rename_map)
    keep = [spec[0] for spec in FIND_SPECS]
    keep = [c for c in keep if c in df.columns]
    df = df[keep].copy()

    for col in df.columns:
        if col not in ("sample_id", "feed_name", "location"):
            df[col] = df[col].apply(_num)

    return df.dropna(subset=["sample_id"]).reset_index(drop=True)


def analyze_feeds(df: pd.DataFrame) -> dict:
    result = {"samples": [], "leaders": {}, "ratings": []}
    numeric_keys = ["DM", "starch", "sugar", "NDF", "ADF", "NDFd", "dOM",
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
        "max_starch": _leader("starch", True),
        "max_sugar":  _leader("sugar", True),
        "min_NDF":    _leader("NDF", False),
        "max_dOM":    _leader("dOM", True),
        "max_NEL_VC": _leader("NEL_VC", True),
        "best_RNB":   _leader("RNB", True),
    }

    # Балл без вклада СП
    for s in result["samples"]:
        score = 0.0
        if s["NEL_VC"] is not None: score += (s["NEL_VC"] - 6.5) * 30
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
            "DM": s["DM"], "Крахмал": s["starch"],
            "Сахар": s["sugar"], "НДК": s["NDF"], "КДК": s["ADF"],
            "Перев. ОВ, %": s["dOM"], "NEL": s["NEL"], "NEL-VC": s["NEL_VC"],
            "nXP": s["nXP"], "RNB": s["RNB"], "Балл": s["score"],
        })
    return pd.DataFrame(rows)
