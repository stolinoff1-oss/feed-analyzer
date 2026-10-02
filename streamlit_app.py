import os
import base64
import streamlit as st
import pandas as pd
import tempfile
import plotly.express as px
import plotly.graph_objects as go

from feed_analyzer import (load_feed_data, analyze_feeds,
                            feeds_to_dataframe, dataframe_from_input)
try:
    from ration_calculator import (calculate_ration, ration_to_dataframe,
                                    DEFAULT_FEEDS_LIBRARY)
except ImportError:
    from ration_calculator import calculate_ration, ration_to_dataframe
    DEFAULT_FEEDS_LIBRARY = {
        "сено":           {"DM": 850, "NEL": 5.8,  "nXP": 130, "NDF": 550,
                            "starch": 5,   "RNB": -4,  "CP": 100},
        "сенаж":          {"DM": 450, "NEL": 6.5,  "nXP": 150, "NDF": 450,
                            "starch": 20,  "RNB": -6,  "CP": 120},
        "комбикорм":      {"DM": 880, "NEL": 8.2,  "nXP": 160, "NDF": 250,
                            "starch": 250, "RNB": -2,  "CP": 150},
        "защищённый жир": {"DM": 990, "NEL": 30.0, "nXP": 0,   "NDF": 0,
                            "starch": 0,   "RNB": 0,   "CP": 0},
        "соевый шрот":    {"DM": 900, "NEL": 8.0,  "nXP": 220, "NDF": 130,
                            "starch": 30,  "RNB": 3,   "CP": 450},
    }

from api_client import get_ai_recommendation, build_context
from pdf_report import generate_pdf
from page_economics import render_economics_page

CONTACT_EMAIL = "viktar.hrechka@syngenta.com"
LOGO_HEIGHT = 75
LOGO_HEIGHT_CENTER = 110

st.set_page_config(page_title="Анализ кормов", page_icon="🐄", layout="wide")


def _safe(d, key, default=0.0):
    if not isinstance(d, dict):
        return default
    v = d.get(key, default)
    if v is None:
        return default
    try:
        f = float(v)
        if f != f:
            return default
        return f
    except (TypeError, ValueError):
        return default


def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets.get("app_password", "12345"):
            st.session_state["authenticated"] = True
            del st.session_state["password"]
        else:
            st.session_state["authenticated"] = False

    if "authenticated" not in st.session_state:
        st.text_input("Пароль", type="password",
                      on_change=password_entered, key="password")
        return False
    elif not st.session_state["authenticated"]:
        st.text_input("Пароль", type="password",
                      on_change=password_entered, key="password")
        st.error("Неверный пароль")
        return False
    return True


if not check_password():
    st.stop()


# ================== ЛОГОТИПЫ + EMAIL ==================
def _img_base64(path):
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _logo_html(path, height=LOGO_HEIGHT):
    b64 = _img_base64(path)
    if not b64:
        return "<div></div>"
    return (f'<img src="data:image/png;base64,{b64}" '
            f'style="height:{height}px; max-width:100%; object-fit:contain;">')


l1 = _logo_html("logo1.png", height=LOGO_HEIGHT)
l2 = _logo_html("logo2.png", height=LOGO_HEIGHT_CENTER)
l3 = _logo_html("logo3.png", height=LOGO_HEIGHT)

st.markdown(
    f"""
    <div style="display:flex; justify-content:space-between; align-items:center;
                padding:14px 10px 0 10px; border-bottom:1px solid #ECF0F1;">
        <div style="flex:0 0 25%; text-align:left;">{l1}</div>
        <div style="flex:0 0 50%; text-align:center;">{l2}</div>
        <div style="flex:0 0 25%; text-align:right;">{l3}</div>
    </div>
    <div style="text-align:right; color:#2C7A3E; font-size:12px;
                padding:4px 10px 0 0;">
        По всем вопросам:
        <a href="mailto:{CONTACT_EMAIL}"
           style="color:#2C7A3E; text-decoration:underline;">
            {CONTACT_EMAIL}
        </a>
    </div>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    "<h1 style='text-align:center; color:#2C7A3E; "
    "margin-top:16px; margin-bottom:2px; font-size:32px;'>"
    "🐄 Анализ кормов и расчёт рационов</h1>",
    unsafe_allow_html=True,
)
st.markdown(
    "<p style='text-align:center; color:#7F8C8D; font-size:13px; "
    "margin-top:0; margin-bottom:20px;'>"
    "Лабораторный анализ силоса • рекомендации по рациону "
    "• оценка качества • экономика выращивания</p>",
    unsafe_allow_html=True,
)
st.markdown("---")


# ================== ВЫБОР СТРАНИЦЫ ==================
with st.sidebar:
    st.header("Страница")
    page = st.radio(
        "Переключение:",
        ["🌽 Анализ кормов", "💰 Экономика выращивания"],
        key="page_select",
        label_visibility="collapsed",
    )
    st.markdown("---")


# ================== СТРАНИЦА «ЭКОНОМИКА» ==================
if page == "💰 Экономика выращивания":
    render_economics_page()

    st.markdown("---")
    st.markdown(
        f"<div style='text-align:center; color:#7F8C8D; font-size:12px; "
        f"padding:10px 0;'>По всем вопросам обращаться: "
        f"<a href='mailto:{CONTACT_EMAIL}' style='color:#2C7A3E;'>"
        f"{CONTACT_EMAIL}</a></div>",
        unsafe_allow_html=True,
    )
    st.stop()


# ================== СТРАНИЦА «АНАЛИЗ КОРМОВ» ==================

with st.sidebar:
    st.header("Параметры коровы")
    live_weight = st.number_input("Живая масса, кг", value=650, step=10)
    milk_yield = st.number_input("Удой, кг/сут", value=35.0, step=0.5)

    st.markdown("---")
    st.header("🌾 Мои корма")
    st.caption("Настройте параметры кормов. "
               "По умолчанию — стандартные справочные значения.")

    feeds_override = {}

    with st.expander("Сено", expanded=False):
        d = DEFAULT_FEEDS_LIBRARY["сено"]
        hay_dm = st.number_input("Сухая масса, г/кг",
                                  300.0, 950.0, float(d.get("DM", 850)), 5.0,
                                  key="my_hay_dm")
        hay_nel = st.number_input("NEL, МДж/кг СВ",
                                   3.0, 12.0, float(d.get("NEL", 5.8)), 0.1,
                                   key="my_hay_nel")
        hay_nxp = st.number_input("nXP, г/кг СВ",
                                   50.0, 300.0, float(d.get("nXP", 130)), 5.0,
                                   key="my_hay_nxp")
        hay_ndf = st.number_input("НДК, г/кг СВ",
                                   200.0, 800.0, float(d.get("NDF", 550)), 5.0,
                                   key="my_hay_ndf")
        hay_starch = st.number_input("Крахмал, г/кг СВ",
                                      0.0, 200.0,
                                      float(d.get("starch", 5)), 1.0,
                                      key="my_hay_starch")
        hay_rnb = st.number_input("RNB, г/кг СВ",
                                   -20.0, 20.0,
                                   float(d.get("RNB", -4)), 0.5,
                                   key="my_hay_rnb")
        hay_cp = st.number_input("Сырой протеин (СП), г/кг СВ",
                                  20.0, 300.0,
                                  float(d.get("CP", 100)), 5.0,
                                  key="my_hay_cp")
        feeds_override["сено"] = {
            "DM": hay_dm, "NEL": hay_nel, "nXP": hay_nxp, "NDF": hay_ndf,
            "starch": hay_starch, "RNB": hay_rnb, "CP": hay_cp,
        }

    with st.expander("Сенаж", expanded=False):
        d = DEFAULT_FEEDS_LIBRARY["сенаж"]
        haylage_dm = st.number_input("Сухая масса, г/кг",
                                      300.0, 700.0,
                                      float(d.get("DM", 450)), 5.0,
                                      key="my_haylage_dm")
        haylage_nel = st.number_input("NEL, МДж/кг СВ",
                                       3.0, 12.0,
                                       float(d.get("NEL", 6.5)), 0.1,
                                       key="my_haylage_nel")
        haylage_nxp = st.number_input("nXP, г/кг СВ",
                                       50.0, 300.0,
                                       float(d.get("nXP", 150)), 5.0,
                                       key="my_haylage_nxp")
        haylage_ndf = st.number_input("НДК, г/кг СВ",
                                       200.0, 800.0,
                                       float(d.get("NDF", 450)), 5.0,
                                       key="my_haylage_ndf")
        haylage_starch = st.number_input("Крахмал, г/кг СВ",
                                          0.0, 300.0,
                                          float(d.get("starch", 20)), 1.0,
                                          key="my_haylage_starch")
        haylage_rnb = st.number_input("RNB, г/кг СВ",
                                       -20.0, 20.0,
                                       float(d.get("RNB", -6)), 0.5,
                                       key="my_haylage_rnb")
        haylage_cp = st.number_input("Сырой протеин (СП), г/кг СВ",
                                      20.0, 300.0,
                                      float(d.get("CP", 120)), 5.0,
                                      key="my_haylage_cp")
        feeds_override["сенаж"] = {
            "DM": haylage_dm, "NEL": haylage_nel,
            "nXP": haylage_nxp, "NDF": haylage_ndf,
            "starch": haylage_starch, "RNB": haylage_rnb,
            "CP": haylage_cp,
        }

    with st.expander("Комбикорм", expanded=False):
        d = DEFAULT_FEEDS_LIBRARY["комбикорм"]
        conc_dm = st.number_input("Сухая масса, г/кг",
                                   600.0, 950.0,
                                   float(d.get("DM", 880)), 5.0,
                                   key="my_conc_dm")
        conc_nel = st.number_input("NEL, МДж/кг СВ",
                                    5.0, 12.0,
                                    float(d.get("NEL", 8.2)), 0.1,
                                    key="my_conc_nel")
        conc_nxp = st.number_input("nXP, г/кг СВ",
                                    50.0, 300.0,
                                    float(d.get("nXP", 160)), 5.0,
                                    key="my_conc_nxp")
        conc_ndf = st.number_input("НДК, г/кг СВ",
                                    100.0, 500.0,
                                    float(d.get("NDF", 250)), 5.0,
                                    key="my_conc_ndf")
        conc_starch = st.number_input("Крахмал, г/кг СВ",
                                       0.0, 600.0,
                                       float(d.get("starch", 250)), 5.0,
                                       key="my_conc_starch")
        conc_rnb = st.number_input("RNB, г/кг СВ",
                                    -20.0, 20.0,
                                    float(d.get("RNB", -2)), 0.5,
                                    key="my_conc_rnb")
        conc_cp = st.number_input("Сырой протеин (СП), г/кг СВ",
                                   20.0, 300.0,
                                   float(d.get("CP", 150)), 5.0,
                                   key="my_conc_cp")
        feeds_override["комбикорм"] = {
            "DM": conc_dm, "NEL": conc_nel,
            "nXP": conc_nxp, "NDF": conc_ndf,
            "starch": conc_starch, "RNB": conc_rnb,
            "CP": conc_cp,
        }

    if st.button("↩️ Сбросить корма", key="reset_feeds"):
        for k in ["my_hay_dm", "my_hay_nel", "my_hay_nxp", "my_hay_ndf",
                  "my_hay_starch", "my_hay_rnb", "my_hay_cp",
                  "my_haylage_dm", "my_haylage_nel", "my_haylage_nxp",
                  "my_haylage_ndf", "my_haylage_starch", "my_haylage_rnb",
                  "my_haylage_cp",
                  "my_conc_dm", "my_conc_nel", "my_conc_nxp", "my_conc_ndf",
                  "my_conc_starch", "my_conc_rnb", "my_conc_cp"]:
            if k in st.session_state:
                del st.session_state[k]
        st.rerun()


# ================== ВЫБОР РЕЖИМА ==================
mode = st.radio(
    "Способ ввода данных:",
    ["📁 Загрузить Excel-файл", "✍️ Ввести данные вручную"],
    horizontal=True,
)

df = None

if mode == "📁 Загрузить Excel-файл":
    uploaded = st.file_uploader("Excel-файл с анализами (.xlsx)",
                                 type=["xlsx", "xls"])
    if uploaded is None:
        st.info("👆 Загрузите файл с анализами кормов")
        st.stop()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        tmp.write(uploaded.read())
        filepath = tmp.name

    try:
        df = load_feed_data(filepath)
    except Exception as e:
        st.error(f"Ошибка чтения файла: {e}")
        st.stop()

else:
    n_silos = st.number_input("Сколько силосов добавить?",
                                min_value=1, max_value=30, value=3, step=1)
    st.caption("Заполните данные для каждого силоса.")

    silos_data = []
    for i in range(int(n_silos)):
        with st.expander(f"🌽 Силос №{i+1}", expanded=(i == 0)):
            name = st.text_input("Название *",
                                  value=f"Силос {i+1}", key=f"name_{i}")

            c1, c2, c3 = st.columns(3)
            dm = c1.number_input("Сухая масса, г/кг *", 100.0, 700.0,
                                  350.0, 5.0, key=f"dm_{i}")
            starch = c2.number_input("Крахмал, г/кг СВ", 0.0, 700.0,
                                      350.0, 5.0, key=f"starch_{i}")
            sugar = c3.number_input("Сахар, г/кг СВ", 0.0, 300.0,
                                     80.0, 5.0, key=f"sugar_{i}")

            c1, c2, c3 = st.columns(3)
            ndf = c1.number_input("НДК, г/кг СВ", 0.0, 700.0,
                                   350.0, 5.0, key=f"ndf_{i}")
            adf = c2.number_input("КДК, г/кг СВ", 0.0, 500.0,
                                   180.0, 5.0, key=f"adf_{i}")
            dom = c3.number_input("Переваримость ОВ, %", 50.0, 95.0,
                                   80.0, 0.5, key=f"dom_{i}")

            c1, c2, c3 = st.columns(3)
            nel = c1.number_input("NEL, МДж/кг СВ", 4.0, 10.0,
                                   7.0, 0.1, key=f"nel_{i}")
            nel_vc = c2.number_input("NEL-VC, МДж/кг СВ", 0.0, 10.0,
                                      0.0, 0.1, key=f"nelvc_{i}",
                                      help="0 → использовать NEL")
            nxp = c3.number_input("nXP, г/кг СВ", 0.0, 300.0,
                                   135.0, 1.0, key=f"nxp_{i}")

            c1, c2 = st.columns(2)
            rnb = c1.number_input("RNB, г/кг СВ", -30.0, 30.0,
                                   -10.0, 0.5, key=f"rnb_{i}")
            structure = c2.number_input("Структурный показатель", 0.5, 3.0,
                                          1.5, 0.1, key=f"struct_{i}")

            silos_data.append({
                "id": f"M{i+1:03d}", "name": name,
                "DM": dm, "starch": starch, "sugar": sugar,
                "NDF": ndf, "ADF": adf, "dOM": dom,
                "NEL": nel, "NEL_VC": nel_vc, "nXP": nxp,
                "RNB": rnb, "structure": structure,
            })

    if st.button("🔬 Рассчитать рационы", type="primary"):
        st.session_state["manual_silos"] = silos_data
        st.session_state["manual_count"] = int(n_silos)

    if ("manual_silos" not in st.session_state
            or st.session_state.get("manual_count") != int(n_silos)):
        st.info("👆 Заполните данные и нажмите «Рассчитать рационы»")
        st.stop()

    df = dataframe_from_input(st.session_state["manual_silos"])


# ================== АНАЛИЗ ==================
try:
    analysis = analyze_feeds(df)
    df_analysis = feeds_to_dataframe(analysis)
except Exception as e:
    st.error(f"Ошибка обработки данных: {e}")
    st.stop()

# Сохраняем данные в session_state — чтобы они были доступны
# на странице экономики
st.session_state["analysis_df"] = df_analysis.to_dict(orient="records")
st.session_state["analysis_full"] = analysis

st.success(f"Обработано {len(df)} образцов")


# ================== ВИЗУАЛИЗАЦИЯ ==================
st.header("📊 Визуализация")
chart_df = df_analysis.copy()

st.subheader("Рейтинг по баллу качества")
if chart_df["Балл"].notna().any():
    fig_rating = px.bar(
        chart_df.sort_values("Балл"),
        x="Балл", y="Образец", orientation="h",
        color="Балл", color_continuous_scale="RdYlGn",
        text="Балл", height=350,
    )
    fig_rating.update_traces(texttemplate="%{text:.1f}",
                              textposition="outside")
    fig_rating.update_layout(showlegend=False, coloraxis_showscale=False,
                              margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig_rating, use_container_width=True)

st.subheader("Энергия: NEL-VC (МДж/кг СВ)")
if chart_df["NEL-VC"].notna().any():
    fig_nel = px.bar(
        chart_df.sort_values("NEL-VC", ascending=False),
        x="Образец", y="NEL-VC",
        color="NEL-VC", color_continuous_scale="Blues",
        text="NEL-VC", height=350,
    )
    fig_nel.update_traces(texttemplate="%{text:.2f}",
                           textposition="outside")
    fig_nel.update_layout(coloraxis_showscale=False, xaxis_tickangle=-45,
                           margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig_nel, use_container_width=True)

st.subheader("Углеводный баланс: крахмал, сахар, НДК")
fig_carbs = go.Figure()
fig_carbs.add_trace(go.Bar(name="Крахмал", x=chart_df["Образец"],
                            y=chart_df["Крахмал"], marker_color="#F39C12"))
fig_carbs.add_trace(go.Bar(name="Сахар", x=chart_df["Образец"],
                            y=chart_df["Сахар"], marker_color="#E74C3C"))
fig_carbs.add_trace(go.Bar(name="НДК", x=chart_df["Образец"],
                            y=chart_df["НДК"], marker_color="#27AE60"))
fig_carbs.update_layout(barmode="group", height=400,
                         xaxis_tickangle=-45,
                         margin=dict(l=10, r=10, t=10, b=10),
                         legend=dict(orientation="h", yanchor="bottom",
                                     y=1.02, xanchor="right", x=1))
st.plotly_chart(fig_carbs, use_container_width=True)

st.subheader("Профиль образцов (радар)")
radar_params = {
    "NEL-VC":     ("NEL-VC", True),
    "Крахмал":    ("Крахмал", True),
    "Сахар":      ("Сахар", True),
    "Перев. ОВ":  ("Перев. ОВ, %", True),
    "Низкий НДК": ("НДК", False),
    "RNB":        ("RNB", True),
}
radar_df = pd.DataFrame()
for label, (col, higher_better) in radar_params.items():
    vals = pd.to_numeric(chart_df[col], errors="coerce")
    if vals.notna().sum() == 0:
        continue
    vals = vals.fillna(vals.mean())
    if col == "RNB":
        score = 100 - (vals.abs() - vals.abs().min()) / \
                (vals.abs().max() - vals.abs().min() + 1e-9) * 100
    elif higher_better:
        score = (vals - vals.min()) / (vals.max() - vals.min() + 1e-9) * 100
    else:
        score = (vals.max() - vals) / (vals.max() - vals.min() + 1e-9) * 100
    radar_df[label] = score

if not radar_df.empty and len(radar_df.columns) >= 3:
    fig_radar = go.Figure()
    top_names = chart_df["Образец"].head(3).tolist()
    bottom_name = chart_df["Образец"].iloc[-1] if len(chart_df) > 3 else None
    show_samples = top_names + ([bottom_name] if bottom_name else [])
    palette = ["#2ECC71", "#3498DB", "#F39C12", "#E74C3C"]

    for i, name in enumerate(show_samples):
        idx_list = chart_df[chart_df["Образец"] == name].index
        if not len(idx_list):
            continue
        idx = idx_list[0]
        values = radar_df.loc[idx].tolist()
        fig_radar.add_trace(go.Scatterpolar(
            r=values + [values[0]],
            theta=list(radar_df.columns) + [list(radar_df.columns)[0]],
            fill="toself", name=name,
            line=dict(color=palette[i % len(palette)]),
            opacity=0.6,
        ))

    fig_radar.update_layout(
        polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
        height=500, showlegend=True,
        margin=dict(l=40, r=40, t=40, b=40),
    )
    st.plotly_chart(fig_radar, use_container_width=True)


# ================== ТАБЛИЦА ==================
st.header("📋 Рейтинг образцов (таблица)")
st.dataframe(df_analysis, use_container_width=True)

st.header("🏆 Лидеры по категориям")
leaders = analysis["leaders"]
cols = st.columns(3)
metrics = [
    ("max_starch", "Макс. крахмал", "starch"),
    ("max_NEL_VC", "Макс. NEL-VC", "NEL_VC"),
    ("best_RNB", "Лучший RNB", "RNB"),
]
for col, (key, label, field) in zip(cols, metrics):
    s = leaders.get(key)
    if s:
        val = s.get(field)
        col.metric(label, s["name"], f"{val}" if val is not None else "—")
    else:
        col.metric(label, "—", "")


# ================== РАЦИОНЫ ==================
st.header("🍽️ Расчёт рационов для всех образцов")
st.caption("Доля силоса адаптируется под НДК каждого образца. "
           "Используются параметры кормов из боковой панели «Мои корма».")

rations = {}
for s in analysis["ratings"]:
    r = calculate_ration(s, live_weight, milk_yield,
                          feeds_lib=feeds_override)
    rations[s["name"]] = r

summary_rows = []
for name, r in rations.items():
    comp = r.get("composition", {})
    summary_rows.append({
        "Образец": name,
        "Силос, % СВ": round(_safe(comp, "silo_pct"), 1),
        "Сено, % СВ": round(_safe(comp, "hay_pct"), 1),
        "Сенаж, % СВ": round(_safe(comp, "haylage_pct"), 1),
        "Комбикорм, % СВ": round(_safe(comp, "conc_pct"), 1),
        "Жир, кг": round(_safe(comp, "fat_kg"), 2),
        "Шрот, кг СВ": round(_safe(comp, "soy_dm"), 2),
        "НДК, % СВ": round(_safe(comp, "ndf_pct"), 1),
        "Крахмал, г/кг": round(_safe(comp, "starch_per_dm"), 0),
        "RNB, г/кг": round(_safe(comp, "total_rnb"), 1),
        "NEL, МДж": round(_safe(r.get("total", {}), "NEL"), 1),
        "Δ NEL": round(
            _safe(r.get("total", {}), "NEL")
            - _safe(r.get("norms", {}), "NEL"), 1),
        "nXP, г": round(_safe(r.get("total", {}), "nXP"), 0),
        "Δ nXP": round(
            _safe(r.get("total", {}), "nXP")
            - _safe(r.get("norms", {}), "nXP"), 0),
        "Предупр.": len(r.get("warnings", [])),
    })
summary_df = pd.DataFrame(summary_rows)

st.subheader("Структура рационов по всем образцам")
st.dataframe(summary_df, use_container_width=True)

st.subheader("Структура рационов (визуализация)")
fig_struct = go.Figure()
fig_struct.add_trace(go.Bar(name="Силос", x=summary_df["Образец"],
                             y=summary_df["Силос, % СВ"], marker_color="#F39C12"))
fig_struct.add_trace(go.Bar(name="Сено", x=summary_df["Образец"],
                             y=summary_df["Сено, % СВ"], marker_color="#8B4513"))
fig_struct.add_trace(go.Bar(name="Сенаж", x=summary_df["Образец"],
                             y=summary_df["Сенаж, % СВ"], marker_color="#27AE60"))
fig_struct.add_trace(go.Bar(name="Комбикорм", x=summary_df["Образец"],
                             y=summary_df["Комбикорм, % СВ"], marker_color="#3498DB"))
fig_struct.update_layout(barmode="stack", height=400,
                          xaxis_tickangle=-45,
                          yaxis_title="% от СВ",
                          margin=dict(l=10, r=10, t=10, b=10),
                          legend=dict(orientation="h", yanchor="bottom",
                                      y=1.02, xanchor="right", x=1))
st.plotly_chart(fig_struct, use_container_width=True)

st.subheader("Детализация по образцам")
for i, (name, r) in enumerate(rations.items()):
    comp = r.get("composition", {})
    warnings = r.get("warnings", [])
    warn_emoji = "⚠️" if warnings else "✅"
    with st.expander(f"{i+1}. {name} {warn_emoji}", expanded=False):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("NEL, МДж",
                  f"{_safe(r.get('total', {}), 'NEL'):.1f}",
                  f"{_safe(r.get('total', {}), 'NEL') - _safe(r.get('norms', {}), 'NEL'):+.1f}")
        c2.metric("nXP, г",
                  f"{_safe(r.get('total', {}), 'nXP'):.0f}",
                  f"{_safe(r.get('total', {}), 'nXP') - _safe(r.get('norms', {}), 'nXP'):+.0f}")
        c3.metric("НДК, % СВ",
                  f"{_safe(comp, 'ndf_pct'):.1f}",
                  f"{_safe(comp, 'ndf_pct') - 34:+.1f}")
        c4.metric("Крахмал, г/кг СВ",
                  f"{_safe(comp, 'starch_per_dm'):.0f}",
                  f"{_safe(comp, 'starch_per_dm') - 250:+.0f}")

        c5, c6 = st.columns(2)
        c5.metric("СВ, кг",
                  f"{_safe(r.get('total', {}), 'dm'):.2f}",
                  f"{_safe(r.get('total', {}), 'dm') - _safe(r.get('norms', {}), 'DM'):+.2f}")
        c6.metric("RNB, г/кг СВ",
                  f"{_safe(comp, 'total_rnb'):.1f}",
                  f"{_safe(comp, 'total_rnb'):+.1f}")

        try:
            st.dataframe(ration_to_dataframe(r), use_container_width=True)
        except Exception:
            st.warning("Не удалось построить таблицу рациона.")

        if warnings:
            for w in warnings:
                st.warning(w)
        else:
            st.success("Рацион сбалансирован.")


# ================== ✏️ РЕДАКТИРОВАНИЕ ==================
st.header("✏️ Редактирование рациона")
st.caption("Выберите образец и меняйте состав — баланс NEL, nXP, НДК, "
           "крахмала и RNB пересчитывается в реальном времени.")

silo_inputs = {s["name"]: s for s in analysis["ratings"]}
sel_name = st.selectbox("Образец для редактирования:",
                          list(rations.keys()), key="edit_select")
base_r = rations[sel_name]
comp = base_r.get("composition", {})
prefix = f"edit_{sel_name}_"

col_reset, _ = st.columns([1, 4])
with col_reset:
    if st.button("🔄 Сбросить", help="Вернуть значения по умолчанию"):
        for k in list(st.session_state.keys()):
            if k.startswith(prefix):
                del st.session_state[k]
        st.rerun()

c1, c2 = st.columns(2)
with c1:
    silo_dm = st.slider("Силос, кг СВ", 0.0, 20.0,
                        float(_safe(comp, "silo_dm")), 0.1,
                        key=prefix + "silo")
    hay_dm = st.slider("Сено, кг СВ", 0.0, 10.0,
                       float(_safe(comp, "hay_dm")), 0.1,
                       key=prefix + "hay")
    haylage_dm = st.slider("Сенаж, кг СВ", 0.0, 12.0,
                           float(_safe(comp, "haylage_dm")), 0.1,
                           key=prefix + "haylage")
with c2:
    conc_dm = st.slider("Комбикорм, кг СВ", 0.0, 15.0,
                        float(_safe(comp, "concentrate_dm")), 0.1,
                        key=prefix + "conc")
    fat_kg = st.slider("Защищённый жир, кг", 0.0, 3.0,
                       float(_safe(comp, "fat_kg")), 0.05,
                       key=prefix + "fat")
    soy_dm = st.slider("Соевый шрот, кг СВ", 0.0, 3.0,
                       float(_safe(comp, "soy_dm")), 0.05,
                       key=prefix + "soy")

edited = calculate_ration(
    silo=silo_inputs[sel_name],
    live_weight=live_weight,
    milk_yield=milk_yield,
    custom={
        "silo_dm": silo_dm, "hay_dm": hay_dm,
        "haylage_dm": haylage_dm, "concentrate_dm": conc_dm,
        "fat_kg": fat_kg, "soy_dm": soy_dm,
    },
    feeds_lib=feeds_override,
)

ecomp = edited.get("composition", {})
e1, e2, e3, e4 = st.columns(4)
e1.metric("NEL, МДж",
          f"{_safe(edited.get('total', {}), 'NEL'):.1f}",
          f"{_safe(edited.get('total', {}), 'NEL') - _safe(edited.get('norms', {}), 'NEL'):+.1f}")
e2.metric("nXP, г",
          f"{_safe(edited.get('total', {}), 'nXP'):.0f}",
          f"{_safe(edited.get('total', {}), 'nXP') - _safe(edited.get('norms', {}), 'nXP'):+.0f}")
e3.metric("СВ, кг",
          f"{_safe(edited.get('total', {}), 'dm'):.2f}",
          f"{_safe(edited.get('total', {}), 'dm') - _safe(edited.get('norms', {}), 'DM'):+.2f}")
e4.metric("НДК, % СВ",
          f"{_safe(ecomp, 'ndf_pct'):.1f}",
          f"{_safe(ecomp, 'ndf_pct') - 34:+.1f}")

e5, e6 = st.columns(2)
e5.metric("Крахмал, г/кг СВ",
          f"{_safe(ecomp, 'starch_per_dm'):.0f}",
          f"{_safe(ecomp, 'starch_per_dm') - 250:+.0f}")
e6.metric("RNB, г/кг СВ",
          f"{_safe(ecomp, 'total_rnb'):.1f}",
          f"{_safe(ecomp, 'total_rnb'):+.1f}")

try:
    st.dataframe(ration_to_dataframe(edited), use_container_width=True)
except Exception:
    st.warning("Не удалось построить таблицу отредактированного рациона.")

for w in edited.get("warnings", []):
    st.warning(w)


# ================== AI ==================
st.header("🩺 Рекомендации")
col_a, col_b = st.columns([1, 4])
with col_a:
    refresh = st.button("🔄 Обновить")

context = build_context(analysis, rations, live_weight, milk_yield)

with st.spinner("Делается анализ..."):
    ai_text = get_ai_recommendation(context, force_refresh=refresh)

st.markdown(ai_text)


# ================== PDF ==================
st.divider()
st.header("📄 PDF-отчёт")
st.caption("Содержит: сводную таблицу, все графики, "
           "рационы для всех образцов, выводы ИИ.")

col_btn, col_dl = st.columns(2)
with col_btn:
    if st.button("📄 Подготовить PDF-отчёт", use_container_width=True):
        with st.spinner("Собираем PDF..."):
            try:
                pdf_bytes = generate_pdf(analysis, rations, ai_text,
                                          live_weight, milk_yield)
                st.session_state["pdf_bytes"] = pdf_bytes
                st.success("PDF готов! Нажмите кнопку справа.")
            except Exception as e:
                st.error(f"Ошибка генерации PDF: {e}")

with col_dl:
    if "pdf_bytes" in st.session_state:
        st.download_button(
            "💾 Скачать PDF-отчёт",
            data=st.session_state["pdf_bytes"],
            file_name="feed_report.pdf",
            mime="application/pdf",
            use_container_width=True,
        )


# ================== ПОДВАЛ ==================
st.markdown("---")
st.markdown(
    f"<div style='text-align:center; color:#7F8C8D; font-size:12px; "
    f"padding:10px 0;'>По всем вопросам обращаться: "
    f"<a href='mailto:{CONTACT_EMAIL}' style='color:#2C7A3E;'>"
    f"{CONTACT_EMAIL}</a></div>",
    unsafe_allow_html=True,
)
