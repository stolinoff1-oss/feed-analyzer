import streamlit as st
import pandas as pd
import tempfile
from feed_analyzer import load_feed_data, analyze_feeds, feeds_to_dataframe
from ration_calculator import calculate_ration, ration_to_dataframe
from api_client import get_ai_recommendation

st.set_page_config(page_title="Анализ кормов", page_icon="🐄", layout="wide")

def check_password():
    def password_entered():
        if st.session_state["password"] == st.secrets.get("app_password", "12345"):
            st.session_state["authenticated"] = True
            del st.session_state["password"]
        else:
            st.session_state["authenticated"] = False
    if "authenticated" not in st.session_state:
        st.text_input("Пароль", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["authenticated"]:
        st.text_input("Пароль", type="password", on_change=password_entered, key="password")
        st.error("Неверный пароль")
        return False
    return True

if not check_password():
    st.stop()

st.title("🐄 Анализ кормов и расчёт рационов")

with st.sidebar:
    st.header("Параметры коровы")
    live_weight = st.number_input("Живая масса, кг", value=650, step=10)
    milk_yield = st.number_input("Удой, кг/сут", value=35.0, step=0.5)

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
st.header("📊 Рейтинг образцов")
st.dataframe(df_analysis, use_container_width=True)

st.header("🍽️ Расчёт рационов (топ-2 образца)")
rations = {}
for s in analysis["ratings"][:2]:
    r = calculate_ration(s, live_weight, milk_yield)
    rations[s["name"]] = r

for name, r in rations.items():
    with st.expander(f"Рацион: {name}", expanded=True):
        col1, col2, col3 = st.columns(3)
        col1.metric("NEL, МДж", f"{r['total']['NEL']:.1f}", f"{r['total']['NEL'] - r['norms']['NEL']:+.1f}")
        col2.metric("nXP, г", f"{r['total']['nXP']:.0f}", f"{r['total']['nXP'] - r['norms']['nXP']:+.0f}")
        col3.metric("СВ, кг", f"{r['total']['dm']:.1f}", f"{r['total']['dm'] - r['norms']['DM']:+.1f}")
        st.dataframe(ration_to_dataframe(r), use_container_width=True)

st.header("🩺 Рекомендации зоотехника")
context = "\n".join([f"{s['name']}: СП={s['CP']}, крахмал={s['starch']}, НДК={s['NDF']}, NEL-VC={s['NEL_VC']}, RNB={s['RNB']}" for s in analysis["ratings"]])
ai_text = get_ai_recommendation(context)
st.markdown(ai_text)
