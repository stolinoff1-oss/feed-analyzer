import streamlit as st
import pandas as pd
import tempfile
import plotly.express as px
import plotly.graph_objects as go
from pdf_report import generate_pdf

from feed_analyzer import load_feed_data, analyze_feeds, feeds_to_dataframe
from ration_calculator import calculate_ration, ration_to_dataframe
from api_client import get_ai_recommendation, build_context

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

st.title("🐄 Анализ кормов и расчёт рационов")

# --- Боковая панель ---
with st.sidebar:
    st.header("Параметры коровы")
    live_weight = st.number_input("Живая масса, кг", value=650, step=10)
    milk_yield = st.number_input("Удой, кг/сут", value=35.0, step=0.5)

# --- Загрузка файла ---
uploaded = st.file_uploader("Excel-файл с анализами (.xlsx)", type=["xlsx", "xls"])
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

# Готовим данные для графиков
chart_df = df_analysis.copy()

# --- График 1: Рейтинг (горизонтальный бар) ---
st.subheader("Рейтинг по баллу качества")
fig_rating = px.bar(
    chart_df.sort_values("Балл"),
    x="Балл", y="Образец", orientation="h",
    color="Балл", color_continuous_scale="RdYlGn",
    text="Балл",
    title=None, height=350,
)
fig_rating.update_traces(texttemplate="%{text:.1f}", textposition="outside")
fig_rating.update_layout(showlegend=False, coloraxis_showscale=False,
                          margin=dict(l=10, r=10, t=10, b=10))
st.plotly_chart(fig_rating, use_container_width=True)

# --- График 2: Энергия (NEL-VC) ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("Энергия: NEL-VC (МДж/кг СВ)")
    fig_nel = px.bar(
        chart_df.sort_values("NEL-VC", ascending=False),
        x="Образец", y="NEL-VC",
        color="NEL-VC", color_continuous_scale="Blues",
        text="NEL-VC", height=350,
    )
    fig_nel.update_traces(texttemplate="%{text:.2f}", textposition="outside")
    fig_nel.update_layout(coloraxis_showscale=False, xaxis_tickangle=-45,
                           margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig_nel, use_container_width=True)

with col2:
    st.subheader("Протеин: СП (г/кг СВ)")
    fig_cp = px.bar(
        chart_df.sort_values("СП, г/кг", ascending=False),
        x="Образец", y="СП, г/кг",
        color="СП, г/кг", color_continuous_scale="Greens",
        text="СП, г/кг", height=350,
    )
    fig_cp.update_traces(texttemplate="%{text:.0f}", textposition="outside")
    fig_cp.update_layout(coloraxis_showscale=False, xaxis_tickangle=-45,
                          margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig_cp, use_container_width=True)

# --- График 3: Углеводы (крахмал vs сахар vs НДК) ---
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

# --- График 4: Radar (паутина) ---
st.subheader("Профиль образцов (радар)")

# Параметры для радара — нормализуем к 0..100
radar_params = {
    "NEL-VC": ("NEL-VC", True),
    "СП":     ("СП, г/кг", True),
    "Крахмал": ("Крахмал", True),
    "Сахар":  ("Сахар", True),
    "Перев. ОВ": ("Перев. ОВ, %", True),
    "Низкий НДК": ("НДК", False),  # инвертируем: чем меньше, тем лучше
    "RNB":    ("RNB", True),       # ближе к нулю — лучше
}
radar_df = pd.DataFrame()
for label, (col, higher_better) in radar_params.items():
    vals = pd.to_numeric(chart_df[col], errors="coerce").fillna(0)
    if col == "RNB":
        # Ближе к нулю = лучше. Инвертируем по модулю.
        score = 100 - (vals.abs() - vals.abs().min()) / \
                (vals.abs().max() - vals.abs().min() + 1e-9) * 100
    elif higher_better:
        score = (vals - vals.min()) / (vals.max() - vals.min() + 1e-9) * 100
    else:
        score = (vals.max() - vals) / (vals.max() - vals.min() + 1e-9) * 100
    radar_df[label] = score

fig_radar = go.Figure()
# Показываем топ-3 и худший для контраста
top_names = chart_df["Образец"].head(3).tolist()
bottom_name = chart_df["Образец"].iloc[-1]
show_samples = top_names + [bottom_name]
palette = ["#2ECC71", "#3498DB", "#F39C12", "#E74C3C"]

for i, name in enumerate(show_samples):
    idx = chart_df[chart_df["Образец"] == name].index[0]
    values = radar_df.loc[idx].tolist()
    fig_radar.add_trace(go.Scatterpolar(
        r=values + [values[0]],
        theta=list(radar_df.columns) + [list(radar_df.columns)[0]],
        fill="toself",
        name=name,
        line=dict(color=palette[i % len(palette)]),
        opacity=0.6,
    ))

fig_radar.update_layout(
    polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
    height=500, showlegend=True,
    margin=dict(l=40, r=40, t=40, b=40),
)
st.plotly_chart(fig_radar, use_container_width=True)
st.caption("Показаны 3 лучших образца и 1 худший для сравнения. "
           "Чем больше площадь — тем лучше профиль.")

# --- Таблица рейтинга ---
st.header("📋 Рейтинг образцов (таблица)")
st.dataframe(df_analysis, use_container_width=True)

# --- Лидеры ---
st.header("🏆 Лидеры по категориям")
leaders = analysis["leaders"]
cols = st.columns(4)
metrics = [
    ("max_CP", "Макс. протеин", "CP"),
    ("max_starch", "Макс. крахмал", "starch"),
    ("max_NEL_VC", "Макс. NEL-VC", "NEL_VC"),
    ("best_RNB", "Лучший RNB", "RNB"),
]
for col, (key, label, field) in zip(cols, metrics):
    s = leaders.get(key)
    if s:
        col.metric(label, s["name"], f"{s.get(field)}")

# ================== РАСЧЁТ РАЦИОНОВ ДЛЯ ВСЕХ ОБРАЗЦОВ ==================
st.header("🍽️ Расчёт рационов для всех образцов")

rations = {}
for s in analysis["ratings"]:
    r = calculate_ration(s, live_weight, milk_yield)
    rations[s["name"]] = r

# Сводная таблица «образец → норма / факт»
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

# --- Детальные рационы ---
st.subheader("Детализация по образцам")
st.caption("Нажмите на любой образец, чтобы увидеть полный рацион.")

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

# ================== AI-РЕКОМЕНДАЦИИ ==================
st.header("🩺 Рекомендации зоотехника (ИИ)")

col_a, col_b = st.columns([1, 4])
with col_a:
    refresh = st.button("🔄 Обновить",
                        help="Сгенерировать рекомендации заново")

context = build_context(analysis, rations, live_weight, milk_yield)

with st.spinner("Анализ данных..."):
    ai_text = get_ai_recommendation(context, force_refresh=refresh)

st.markdown(ai_text)

# ================== СКАЧИВАНИЕ ОТЧЁТОВ ==================
st.divider()
st.header("📥 Скачать отчёты")

col_dl1, col_dl2 = st.columns(2)

# --- Excel ---
with col_dl1:
    out_path = tempfile.mktemp(suffix=".xlsx")
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        df_analysis.to_excel(writer, sheet_name="Рейтинг", index=False)
        summary_df.to_excel(writer, sheet_name="Сводка рационов", index=False)
        for name, r in rations.items():
            safe = str(name)[:25].replace("/", "_").replace("\\", "_")
            ration_to_dataframe(r).to_excel(
                writer, sheet_name=f"Рацион_{safe}", index=False)
    with open(out_path, "rb") as f:
        st.download_button(
            "📊 Скачать Excel-отчёт",
            data=f,
            file_name="feed_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

# --- PDF ---
with col_dl2:
    st.caption("PDF-отчёт содержит: сводную таблицу, графики, "
               "рационы для всех образцов и выводы ИИ.")
    if st.button("📄 Подготовить PDF-отчёт", use_container_width=True):
        with st.spinner("Собираем PDF..."):
            try:
                pdf_bytes = generate_pdf(analysis, rations, ai_text,
                                          live_weight, milk_yield)
                st.session_state["pdf_bytes"] = pdf_bytes
                st.success("PDF готов!")
            except Exception as e:
                st.error(f"Ошибка генерации PDF: {e}")

    if "pdf_bytes" in st.session_state:
        st.download_button(
            "📄 Скачать PDF-отчёт",
            data=st.session_state["pdf_bytes"],
            file_name="feed_report.pdf",
            mime="application/pdf",
            use_container_width=True,
        )
