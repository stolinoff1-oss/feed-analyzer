"""UI для страницы «Экономика выращивания» + AI-выводы."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from economics import calculate_economics
from api_client import (get_economics_ai_recommendation,
                         build_economics_context)


def _fmt(x, digits=0):
    if x is None:
        return "—"
    try:
        f = float(x)
        if digits == 0:
            return f"{f:,.0f}".replace(",", " ")
        return f"{f:,.{digits}f}".replace(",", " ")
    except (ValueError, TypeError):
        return str(x)


def _get_sample_params(sample: dict) -> dict:
    """Извлекает из образца анализа параметры для экономики."""
    return {
        "dm_pct": sample.get("DM") and sample["DM"] / 10 or 35,
        "me": sample.get("ME") or 11.0,
        "starch": sample.get("starch"),
        "CP": sample.get("CP"),
        "NDF": sample.get("NDF"),
        "dOM": sample.get("dOM"),
        "RNB": sample.get("RNB"),
    }


def render_economics_page():
    st.header("💰 Экономика выращивания силосной кукурузы")
    st.caption("Сравнение двух гибридов: урожайность, затраты, выход обменной "
               "энергии и экономия. Можно подтянуть параметры из анализа силоса.")

    # ================== ДАННЫЕ ИЗ АНАЛИЗА ==================
    analysis_records = st.session_state.get("analysis_df", [])
    has_analysis = bool(analysis_records)

    use_analysis = False
    if has_analysis:
        use_analysis = st.checkbox(
            f"🔬 Использовать данные из анализа кормов "
            f"(загружено {len(analysis_records)} образцов)",
            value=False,
            help="При включении можно выбрать образец из анализа и его "
                 "СВ% и ОЭ подтянутся автоматически.",
        )
    else:
        st.info("💡 Данные анализа кормов не загружены. "
                "Перейдите на страницу «🌽 Анализ кормов» и загрузите файл — "
                "потом вернитесь сюда, чтобы подтянуть параметры.")

    # Функция: получить список вариантов из анализа
    def _options():
        return ["— ввести вручную —"] + [r.get("Образец", "—")
                                            for r in analysis_records]

    # ================== ОБЩИЕ ПАРАМЕТРЫ ==================
    st.subheader("1. Общие параметры")
    c1, c2 = st.columns(2)
    with c1:
        silo_demand = st.number_input(
            "Потребность в силосе, ц/год",
            min_value=1000, max_value=5_000_000,
            value=170_000, step=1000,
            help="Если цифра в тоннах — умножьте на 10",
        )
    with c2:
        grain_price = st.number_input(
            "Цена кукурузного зерна, руб/т",
            min_value=1000, max_value=200_000,
            value=10_000, step=500,
        )

    # ================== ДВА ГИБРИДА ==================
    st.subheader("2. Параметры гибридов")
    col1, col2 = st.columns(2)

    silenta_extra = None
    competitor_extra = None

    # ----- Гибрид Сингента -----
    with col1:
        st.markdown("### 🌱 Гибрид Сингента")
        s_name = st.text_input("Название",
                                value="Сингента (Кардона)",
                                key="econ_s_name")

        s_selected = None
        if use_analysis and analysis_records:
            s_choice = st.selectbox("Или выбрать из анализа:",
                                     _options(), key="econ_s_choice")
            if s_choice != "— ввести вручную —":
                for r in analysis_records:
                    if r.get("Образец") == s_choice:
                        s_selected = r
                        s_name = s_choice
                        silenta_extra = _get_sample_params(r)
                        break

        # Значения по умолчанию
        s_dm_default = silenta_extra["dm_pct"] if silenta_extra else 34.0
        s_me_default = silenta_extra["me"] if silenta_extra else 10.8

        s_yield = st.number_input("Урожайность ЗМ, ц/га",
                                   50.0, 1500.0, 430.0, 5.0,
                                   key="econ_s_yield")
        s_seed_rate = st.number_input("Норма высева, шт/га",
                                       10_000, 200_000, 75_000, 1000,
                                       key="econ_s_rate")
        s_seed_price = st.number_input("Стоимость 1 п.е. (80 тыс.семян), руб",
                                        1000, 200_000, 16_830, 100,
                                        key="econ_s_price")
        s_field_cost = st.number_input("Затраты на 1 га, руб",
                                        5000, 500_000, 20_000, 500,
                                        key="econ_s_field")
        s_dm = st.number_input("Содержание СВ, %",
                                15.0, 60.0,
                                float(s_dm_default), 0.5,
                                key="econ_s_dm")
        s_me = st.number_input("ОЭ, МДж/кг СВ",
                                5.0, 15.0,
                                float(s_me_default), 0.1,
                                key="econ_s_me")

        if silenta_extra:
            st.caption(
                f"📊 Из анализа: крахмал={silenta_extra['starch']} г/кг, "
                f"СП={silenta_extra['CP']} г/кг, "
                f"НДК={silenta_extra['NDF']} г/кг, "
                f"перев.ОВ={silenta_extra['dOM']}%, "
                f"RNB={silenta_extra['RNB']}"
            )

    # ----- Гибрид конкурента -----
    with col2:
        st.markdown("### 🌾 Гибрид конкурента")
        c_name = st.text_input("Название",
                                value="Краснодарский 230 МВ",
                                key="econ_c_name")

        c_selected = None
        if use_analysis and analysis_records:
            c_choice = st.selectbox("Или выбрать из анализа:",
                                     _options(), key="econ_c_choice")
            if c_choice != "— ввести вручную —":
                for r in analysis_records:
                    if r.get("Образец") == c_choice:
                        c_selected = r
                        c_name = c_choice
                        competitor_extra = _get_sample_params(r)
                        break

        c_dm_default = competitor_extra["dm_pct"] if competitor_extra else 30.0
        c_me_default = competitor_extra["me"] if competitor_extra else 10.4

        c_yield = st.number_input("Урожайность ЗМ, ц/га",
                                   50.0, 1500.0, 400.0, 5.0,
                                   key="econ_c_yield")
        c_seed_rate = st.number_input("Норма высева, шт/га",
                                       10_000, 200_000, 85_000, 1000,
                                       key="econ_c_rate")
        c_seed_price = st.number_input("Стоимость 1 п.е. (80 тыс.семян), руб",
                                        1000, 200_000, 5_634, 100,
                                        key="econ_c_price")
        c_field_cost = st.number_input("Затраты на 1 га, руб",
                                        5000, 500_000, 20_000, 500,
                                        key="econ_c_field")
        c_dm = st.number_input("Содержание СВ, %",
                                15.0, 60.0,
                                float(c_dm_default), 0.5,
                                key="econ_c_dm")
        c_me = st.number_input("ОЭ, МДж/кг СВ",
                                5.0, 15.0,
                                float(c_me_default), 0.1,
                                key="econ_c_me")

        if competitor_extra:
            st.caption(
                f"📊 Из анализа: крахмал={competitor_extra['starch']} г/кг, "
                f"СП={competitor_extra['CP']} г/кг, "
                f"НДК={competitor_extra['NDF']} г/кг, "
                f"перев.ОВ={competitor_extra['dOM']}%, "
                f"RNB={competitor_extra['RNB']}"
            )

    # ================== РАСЧЁТ ==================
    result = calculate_economics(
        silenta={
            "silo_demand": silo_demand, "yield_green": s_yield,
            "seeding_rate": s_seed_rate, "seed_price": s_seed_price,
            "field_cost": s_field_cost, "dm_pct": s_dm,
            "me": s_me, "grain_price": grain_price,
        },
        competitor={
            "silo_demand": silo_demand, "yield_green": c_yield,
            "seeding_rate": c_seed_rate, "seed_price": c_seed_price,
            "field_cost": c_field_cost, "dm_pct": c_dm,
            "me": c_me, "grain_price": grain_price,
        },
    )

    s = result["silenta"]
    c = result["competitor"]

    # ================== СВОДНАЯ ТАБЛИЦА ==================
    st.subheader("3. Сравнение гибридов")
    comparison = pd.DataFrame([
        {"Показатель": "Урожайность ЗМ, ц/га",
         s_name: _fmt(s_yield, 0), c_name: _fmt(c_yield, 0)},
        {"Показатель": "Площадь сева, га",
         s_name: _fmt(s["area"], 1), c_name: _fmt(c["area"], 1)},
        {"Показатель": "Затраты на семена, руб/га",
         s_name: _fmt(s["seed_cost_per_ha"], 0),
         c_name: _fmt(c["seed_cost_per_ha"], 0)},
        {"Показатель": "Затраты на всю площадь, руб",
         s_name: _fmt(s["total_cost"], 0),
         c_name: _fmt(c["total_cost"], 0)},
        {"Показатель": "Содержание СВ, %",
         s_name: _fmt(s_dm, 1), c_name: _fmt(c_dm, 1)},
        {"Показатель": "Урожайность СВ, ц/га",
         s_name: _fmt(s["dm_yield"], 1), c_name: _fmt(c["dm_yield"], 1)},
        {"Показатель": "Валовый сбор СВ, ц",
         s_name: _fmt(s["dm_total"], 0), c_name: _fmt(c["dm_total"], 0)},
        {"Показатель": "ОЭ, МДж/кг СВ",
         s_name: _fmt(s_me, 1), c_name: _fmt(c_me, 1)},
        {"Показатель": "**Выход ОЭ, МДж/га**",
         s_name: f"**{_fmt(s['me_per_ha'], 0)}**",
         c_name: f"**{_fmt(c['me_per_ha'], 0)}**"},
    ])
    st.dataframe(comparison, use_container_width=True, hide_index=True)

    # ================== ЭКОНОМИЯ ==================
    st.subheader("4. Экономия от выбора Сингенты")
    e1, e2, e3, e4 = st.columns(4)
    e1.metric("Освобождено площади", f"{_fmt(result['freed_area'], 1)} га")
    e2.metric("Экономия затрат", f"{_fmt(result['saving_field'], 0)} ₽")
    e3.metric("Разница ОЭ/га", f"{_fmt(result['delta_me_per_ha'], 0)} МДж")
    e4.metric("Эквивалент зерна",
              f"{_fmt(result['grain_equiv_per_ha'], 0)} кг/га")

    st.markdown("---")
    total_col1, total_col2, total_col3 = st.columns(3)
    total_col1.metric("Экономия на зерне",
                       f"{_fmt(result['saving_grain'], 0)} ₽")
    total_col2.metric("💰 Общая экономия",
                       f"{_fmt(result['total_saving'], 0)} ₽")
    total_col3.metric("Экономия на гектар",
                       f"{_fmt(result['total_saving_per_ha'], 0)} ₽/га")

    if result["total_saving"] > 0:
        st.success(
            f"**{s_name}** обеспечивает экономию "
            f"**{_fmt(result['total_saving'], 0)} ₽** "
            f"({_fmt(result['total_saving_per_ha'], 0)} ₽/га) "
            f"по сравнению с **{c_name}**."
        )
    else:
        st.warning(f"**{s_name}** не даёт преимущества при текущих параметрах.")

    # ================== ГРАФИКИ ==================
    st.subheader("5. Графики сравнения")
    g1, g2 = st.columns(2)
    with g1:
        fig_me = go.Figure(data=[
            go.Bar(name=s_name, x=["МДж/га"], y=[s["me_per_ha"]],
                   marker_color="#2C7A3E", text=[_fmt(s["me_per_ha"], 0)],
                   textposition="outside"),
            go.Bar(name=c_name, x=["МДж/га"], y=[c["me_per_ha"]],
                   marker_color="#7F8C8D", text=[_fmt(c["me_per_ha"], 0)],
                   textposition="outside"),
        ])
        fig_me.update_layout(height=350, showlegend=True,
                              margin=dict(l=10, r=10, t=40, b=10),
                              title="Выход ОЭ с гектара")
        st.plotly_chart(fig_me, use_container_width=True)

    with g2:
        fig_cost = go.Figure(data=[
            go.Bar(name=s_name, x=["Затраты, ₽"], y=[s["total_cost"]],
                   marker_color="#2C7A3E", text=[_fmt(s["total_cost"], 0)],
                   textposition="outside"),
            go.Bar(name=c_name, x=["Затраты, ₽"], y=[c["total_cost"]],
                   marker_color="#7F8C8D", text=[_fmt(c["total_cost"], 0)],
                   textposition="outside"),
        ])
        fig_cost.update_layout(height=350, showlegend=True,
                                margin=dict(l=10, r=10, t=40, b=10),
                                title="Затраты на всю площадь")
        st.plotly_chart(fig_cost, use_container_width=True)

    # ================== AI-ВЫВОДЫ ==================
    st.markdown("---")
    st.subheader("6. 🩺 Экономический вывод (ИИ)")

    col_a, col_b = st.columns([1, 4])
    with col_a:
        refresh_econ = st.button("🔄 Обновить", key="econ_ai_refresh")

    econ_context = build_economics_context(
        result, s_name, c_name,
        silenta_extra=silenta_extra,
        competitor_extra=competitor_extra,
    )

    with st.spinner("AI анализирует экономику..."):
        econ_ai_text = get_economics_ai_recommendation(
            econ_context, force_refresh=refresh_econ
        )

    st.markdown(econ_ai_text)

    # ================== ИТОГ ==================
    st.markdown("---")
    st.info(
        "**Как считается экономия:**\n\n"
        "1. Разница в выходе ОЭ (МДж/га) переводится в эквивалент "
        "кукурузного зерна (1 кг зерна = 12.835 МДж).\n\n"
        "2. Эквивалент × цена зерна = экономия на покупке зерна.\n\n"
        "3. Плюс — экономия затрат на выращивание за счёт меньшей площади."
    )
