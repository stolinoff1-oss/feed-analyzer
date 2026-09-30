import os
import base64
import streamlit as st
import pandas as pd
import tempfile
import plotly.express as px
import plotly.graph_objects as go

from feed_analyzer import load_feed_data, analyze_feeds, feeds_to_dataframe
from ration_calculator import calculate_ration, ration_to_dataframe
from api_client import get_ai_recommendation, build_context
from pdf_report import generate_pdf

# === КОНТАКТ ===
CONTACT_EMAIL = "viktar.hrechka@syngenta.com"

# === РАЗМЕР ЛОГОТИПОВ (высота в пикселях) ===
LOGO_HEIGHT = 60


st.set_page_config(page_title="Анализ кормов", page_icon="🐄", layout="wide")


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


# ================== ЛОГОТИПЫ (base64, одинаковая высота) ==================
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


l1 = _logo_html("logo1.png")
l2 = _logo_html("logo2.png")
l3 = _logo_html("logo3.png")

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

# ================== ЗАГОЛОВОК ==================
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
    "• оценка качества</p>",
    unsafe_allow_html=True,
)
st.markdown("---")


# ================== БОКОВАЯ ПАНЕЛЬ ==================
with st.sidebar:
    st.header("Параметры коровы")
    live_weight = st.number_input("Живая масса, кг", value=650, step=10)
    milk_yield = st.number_input("Удой, кг/сут", value=35.0, step=0.5)


# ================== ЗАГРУЗКА ФАЙЛА ==================
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
    analysis = analyze_feeds(df)
    df_analysis = feeds_to_dataframe(analysis)
except Exception as e:
    st.error(f"Ошибка чтения файла: {e}")
    st.stop()

st.success(f"Загружено {len(df)} образцов")

# ================== ВИЗУАЛИЗАЦИЯ ==================
st.header("📊 Визуализация")

chart_df = df_analysis.copy()

# --- Рейтинг ---
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
else:
    st.warning("Нет данных для построения рейтинга.")

# --- Энергия ---
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

# --- Углеводы ---
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

# --- Radar ---
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
    st.caption("Показаны 3 лучших образца и 1 худший для сравнения.")

# --- Таблица ---
st.header("📋 Рейтинг образцов (таблица)")
st.dataframe(df_analysis, use_container_width=True)

# --- Лидеры ---
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

rations = {}
for s in analysis["ratings"]:
    r = calculate_ration(s, live_weight, milk_yield)
    rations[s["name"]] = r

summary_rows = []
for name, r in rations.items():
    summary_rows.append({
        "Образец": name,
        "NEL, МДж": round(r["total"]["NEL"], 1),
        "Норма NEL": r["norms"]["NEL"],
        "Δ NEL": round(r["total"]["NEL"] - r["norms"]["NEL"], 1),
        "nXP, г": round(r["total"]["nXP"], 0),
        "Норма nXP": r["norms"]["nXP"],
        "Δ nXP": round(r["total"]["nXP"] - r["norms"]["nXP"], 0),
        "СВ, кг": round(r["total"]["dm"], 2),
        "Корректировок": len(r["corrections"]),
    })
summary_df = pd.DataFrame(summary_rows)

st.subheader("Сводная таблица по всем образцам")
st.dataframe(summary_df, use_container_width=True)

st.subheader("Детализация по образцам")

for i, (name, r) in enumerate(rations.items()):
    with st.expander(f"{i+1}. {name}", expanded=False):
        c1, c2, c3 = st.columns(3)
        c1.metric("NEL, МДж",
                  f"{r['total']['NEL']:.1f}",
                  f"{r['total']['NEL'] - r['norms']['NEL']:+.1f}")
        c2.metric("nXP, г",
                  f"{r['total']['nXP']:.0f}",
                  f"{r['total']['nXP'] - r['norms']['nXP']:+.0f}")
        c3.metric("СВ, кг",
                  f"{r['total']['dm']:.2f}",
                  f"{r['total']['dm'] - r['norms']['DM']:+.2f}")

        st.dataframe(ration_to_dataframe(r), use_container_width=True)

        if r["corrections"]:
            st.warning("Корректировки: " +
                       "; ".join(str(c) for c in r["corrections"]))
        else:
            st.success("Корректировки не требуются.")

# ================== AI ==================
st.header("🩺 Рекомендации зоотехника (ИИ)")

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
