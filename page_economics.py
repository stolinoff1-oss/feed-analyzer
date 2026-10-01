"""UI для страницы «Экономика выращивания» + экономия на кормах + AI + PDF."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from economics import calculate_economics, calc_feed_economics
from api_client import (get_economics_ai_recommendation,
                         build_economics_context)
from pdf_report import generate_economics_pdf


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
    dm_kg = sample.get("DM")
    dm_pct = dm_kg / 10 if dm_kg else 35.0
    me = sample.get("ME")
    if not me:
        me = sample.get("NEL-VC") or sample.get("NEL_VC") or 11.0
    return {
        "dm_pct": dm_pct,
        "me": me,
        "starch": sample.get("Крахмал"),
        "CP": sample.get("СП, г/кг") or sample.get("CP"),
        "NDF": sample.get("НДК"),
        "dOM": sample.get("Перев. ОВ, %"),
        "RNB": sample.get("RNB"),
        "nXP": sample.get("nXP"),
        "NEL": sample.get("NEL"),
        "NEL_VC": sample.get("NEL-VC") or sample.get("NEL_VC"),
        "ADF": sample.get("КДК"),
        "sugar": sample.get("Сахар"),
    }


def _sample_to_silo(sample_params: dict) -> dict:
    """Преобразует извлечённые из анализа параметры в формат для
    calculate_ration()."""
    return {
        "DM": sample_params["dm_pct"] * 10,   # % → г/кг
        "starch": sample_params.get("starch") or 350,
        "sugar": sample_params.get("sugar") or 0,
        "NDF": sample_params.get("NDF") or 350,
        "ADF": sample_params.get("ADF") or 180,
        "dOM": sample_params.get("dOM") or 80,
        "NEL": sample_params.get("NEL") or sample_params["me"],
        "NEL_VC": sample_params.get("NEL_VC") or sample_params["me"],
        "nXP": sample_params.get("nXP") or 135,
        "RNB": sample_params.get("RNB") if sample_params.get("RNB") is not None else -10,
        "structure": 1.5,
    }


def render_economics_page():
    st.header("💰 Экономика выращивания силосной кукурузы")
    st.caption("Сравнение двух гибридов и расчёт экономии — при выращивании "
               "и при кормлении. Все суммы — в валюте расчёта.")

    # ================== ДАННЫЕ ИЗ АНАЛИЗА ==================
    analysis_records = st.session_state.get("analysis_df", [])
    has_analysis = bool(analysis_records)

    use_analysis = False
    if has_analysis:
        use_analysis = st.checkbox(
            f"🔬 Использовать данные из анализа кормов "
            f"(загружено {len(analysis_records)} образцов)",
            value=False,
            help="При включении можно выбрать образец — СВ%, ОЭ, крахмал, "
                 "НДК, nXP подтянутся автоматически.",
        )
    else:
        st.info("💡 Данные анализа кормов не загружены. "
                "Перейдите на страницу «🌽 Анализ кормов» и загрузите файл — "
                "потом вернитесь сюда, чтобы подтянуть параметры.")

    def _options():
        return ["— ввести вручную —"] + [r.get("Образец", "—")
                                            for r in analysis_records]

    # ================== ОБЩИЕ ПАРАМЕТРЫ ==================
    st.subheader("1. Общие параметры (выращивание)")
    c1, c2 = st.columns(2)
    with c1:
        silo_demand_t = st.number_input(
            "Потребность в силосе, т/год",
            value=17_000.0, step=100.0, format="%.1f",
            help="В тоннах. Внутри 1 т = 10 ц.",
        )
    with c2:
        grain_price = st.number_input(
            "Цена кукурузного зерна, за 1 т (в валюте расчёта)",
            value=10_000.0, step=500.0, format="%.0f",
            help="BYN, RUB, KZT — в одной валюте, без пересчёта.",
        )

    silo_demand_c = silo_demand_t * 10

    # ================== ДВА ГИБРИДА ==================
    st.subheader("2. Параметры гибридов (силосов)")
    col1, col2 = st.columns(2)

    silenta_extra = None
    competitor_extra = None

    # ----- Гибрид Сингента -----
    with col1:
        st.markdown("### 🌱 Гибрид Сингента")
        s_name = st.text_input("Название",
                                value="Сингента (Кардона)",
                                key="econ_s_name")

        if use_analysis and analysis_records:
            s_choice = st.selectbox("Или выбрать из анализа:",
                                     _options(), key="econ_s_choice")
            if s_choice != "— ввести вручную —":
                for r in analysis_records:
                    if r.get("Образец") == s_choice:
                        s_name = s_choice
                        silenta_extra = _get_sample_params(r)
                        break

        s_yield = st.number_input("Урожайность ЗМ, ц/га",
                                    value=430.0, step=5.0, format="%.1f",
                                    key="econ_s_yield")
        s_seed_rate = st.number_input("Норма высева, шт/га",
                                        value=75_000.0, step=1_000.0,
                                        format="%.0f", key="econ_s_rate")
        s_seed_price = st.number_input(
            "Стоимость 1 п.е. (80 тыс.семян), в валюте расчёта",
            value=16_830.0, step=100.0, format="%.0f",
            key="econ_s_price")
        s_field_cost = st.number_input(
            "Затраты на 1 га, в валюте расчёта",
            value=20_000.0, step=500.0, format="%.0f",
            key="econ_s_field")

        if silenta_extra:
            s_dm = silenta_extra["dm_pct"]
            s_me = silenta_extra["me"]
            st.markdown("**Из лабораторного анализа:**")
            m1, m2 = st.columns(2)
            m1.metric("СВ, %", f"{s_dm:.1f}")
            m2.metric("ОЭ, МДж/кг СВ", f"{s_me:.2f}")
            st.caption("🔒 Значения подтянуты из анализа.")
        else:
            s_dm = st.number_input("Содержание СВ, %",
                                     value=34.0, step=0.5, format="%.1f",
                                     key="econ_s_dm")
            s_me = st.number_input("ОЭ, МДж/кг СВ",
                                     value=10.8, step=0.1, format="%.2f",
                                     key="econ_s_me")

    # ----- Гибрид конкурента -----
    with col2:
        st.markdown("### 🌾 Гибрид конкурента")
        c_name = st.text_input("Название",
                                value="Краснодарский 230 МВ",
                                key="econ_c_name")

        if use_analysis and analysis_records:
            c_choice = st.selectbox("Или выбрать из анализа:",
                                     _options(), key="econ_c_choice")
            if c_choice != "— ввести вручную —":
                for r in analysis_records:
                    if r.get("Образец") == c_choice:
                        c_name = c_choice
                        competitor_extra = _get_sample_params(r)
                        break

        c_yield = st.number_input("Урожайность ЗМ, ц/га",
                                    value=400.0, step=5.0, format="%.1f",
                                    key="econ_c_yield")
        c_seed_rate = st.number_input("Норма высева, шт/га",
                                        value=85_000.0, step=1_000.0,
                                        format="%.0f", key="econ_c_rate")
        c_seed_price = st.number_input(
            "Стоимость 1 п.е. (80 тыс.семян), в валюте расчёта",
            value=5_634.0, step=100.0, format="%.0f",
            key="econ_c_price")
        c_field_cost = st.number_input(
            "Затраты на 1 га, в валюте расчёта",
            value=20_000.0, step=500.0, format="%.0f",
            key="econ_c_field")

        if competitor_extra:
            c_dm = competitor_extra["dm_pct"]
            c_me = competitor_extra["me"]
            st.markdown("**Из лабораторного анализа:**")
            m1, m2 = st.columns(2)
            m1.metric("СВ, %", f"{c_dm:.1f}")
            m2.metric("ОЭ, МДж/кг СВ", f"{c_me:.2f}")
            st.caption("🔒 Значения подтянуты из анализа.")
        else:
            c_dm = st.number_input("Содержание СВ, %",
                                     value=30.0, step=0.5, format="%.1f",
                                     key="econ_c_dm")
            c_me = st.number_input("ОЭ, МДж/кг СВ",
                                     value=10.4, step=0.1, format="%.2f",
                                     key="econ_c_me")

    # ================== ПРОВЕРКИ ==================
    warn_list = []
    if s_yield <= 0 or c_yield <= 0:
        warn_list.append("⚠️ Урожайность должна быть больше 0.")
    if s_dm <= 0 or c_dm <= 0:
        warn_list.append("⚠️ Содержание СВ должно быть больше 0.")
    if s_me <= 0 or c_me <= 0:
        warn_list.append("⚠️ ОЭ должна быть больше 0.")
    if silo_demand_t <= 0:
        warn_list.append("⚠️ Потребность в силосе должна быть больше 0.")
    for w in warn_list:
        st.warning(w)
    if s_yield <= 0 or c_yield <= 0:
        st.error("Невозможно рассчитать: урожайность = 0.")
        return

    # ================== РАСЧЁТ ВЫРАЩИВАНИЯ ==================
    result = calculate_economics(
        silenta={"silo_demand": silo_demand_c, "yield_green": s_yield,
                  "seeding_rate": s_seed_rate, "seed_price": s_seed_price,
                  "field_cost": s_field_cost, "dm_pct": s_dm,
                  "me": s_me, "grain_price": grain_price},
        competitor={"silo_demand": silo_demand_c, "yield_green": c_yield,
                     "seeding_rate": c_seed_rate, "seed_price": c_seed_price,
                     "field_cost": c_field_cost, "dm_pct": c_dm,
                     "me": c_me, "grain_price": grain_price},
    )

    s = result["silenta"]
    c = result["competitor"]

    # ================== СВОДНАЯ ТАБЛИЦА ==================
    st.subheader("3. Сравнение гибридов")
    comparison = pd.DataFrame([
        {"Показатель": "Урожайность ЗМ, ц/га",
         s_name: _fmt(s_yield, 1), c_name: _fmt(c_yield, 1)},
        {"Показатель": "Площадь сева, га",
         s_name: _fmt(s["area"], 1), c_name: _fmt(c["area"], 1)},
        {"Показатель": "Затраты на семена, на 1 га",
         s_name: _fmt(s["seed_cost_per_ha"], 0),
         c_name: _fmt(c["seed_cost_per_ha"], 0)},
        {"Показатель": "Затраты на всю площадь",
         s_name: _fmt(s["total_cost"], 0),
         c_name: _fmt(c["total_cost"], 0)},
        {"Показатель": "Содержание СВ, %",
         s_name: _fmt(s_dm, 1), c_name: _fmt(c_dm, 1)},
        {"Показатель": "Урожайность СВ, ц/га",
         s_name: _fmt(s["dm_yield"], 1), c_name: _fmt(c["dm_yield"], 1)},
        {"Показатель": "Валовый сбор СВ, ц",
         s_name: _fmt(s["dm_total"], 0), c_name: _fmt(c["dm_total"], 0)},
        {"Показатель": "ОЭ, МДж/кг СВ",
         s_name: _fmt(s_me, 2), c_name: _fmt(c_me, 2)},
        {"Показатель": "**Выход ОЭ, МДж/га**",
         s_name: f"**{_fmt(s['me_per_ha'], 0)}**",
         c_name: f"**{_fmt(c['me_per_ha'], 0)}**"},
    ])
    st.dataframe(comparison, use_container_width=True, hide_index=True)

    # ================== ЭКОНОМИЯ НА ВЫРАЩИВАНИИ ==================
    st.subheader("4. Экономия на выращивании")

    e1, e2, e3, e4 = st.columns(4)
    e1.metric("Освобождено площади", f"{_fmt(result['freed_area'], 1)} га")
    e2.metric("Экономия затрат", f"{_fmt(result['saving_field'], 0)}")
    e3.metric("Разница ОЭ/га",
              f"{_fmt(result['delta_me_per_ha'], 0)} МДж")
    e4.metric("Эквивалент зерна",
              f"{_fmt(result['grain_equiv_per_ha'], 0)} кг/га")

    total_col1, total_col2 = st.columns(2)
    total_col1.metric("Экономия на зерне",
                       f"{_fmt(result['saving_grain'], 0)}")
    total_col2.metric("💰 Общая экономия на выращивании (в год)",
                       f"{_fmt(result['total_saving'], 0)}")

    if result["total_saving"] > 0:
        st.success(
            f"**{s_name}** обеспечивает экономию на выращивании "
            f"**{_fmt(result['total_saving'], 0)}** "
            f"({_fmt(result['total_saving_per_ha'], 0)} /га)."
        )
    elif result["total_saving"] < 0:
        st.error(f"При текущих параметрах **{s_name}** проигрывает "
                 f"**{c_name}** на {_fmt(abs(result['total_saving']), 0)}.")

    # ================== ЭКОНОМИЯ НА КОРМАХ ==================
    st.markdown("---")
    st.subheader("5. Экономия на кормах (для заданного удоя)")
    st.caption("Сколько силоса и комбикорма нужно каждой корове при "
               "использовании силоса Сингенты vs конкурента. "
               "Экономия — в день и год.")

    # Параметры кормления
    feed_col1, feed_col2, feed_col3 = st.columns(3)
    with feed_col1:
        live_weight_f = st.number_input(
            "Живая масса коровы, кг",
            value=650.0, step=10.0, format="%.0f", key="feed_lw")
        milk_yield_f = st.number_input(
            "Удой, кг/сут",
            value=35.0, step=0.5, format="%.1f", key="feed_my")
    with feed_col2:
        n_cows = st.number_input(
            "Поголовье, голов",
            value=400, step=10, key="feed_ncows")
        conc_price_t = st.number_input(
            "Цена комбикорма, за 1 т",
            value=3500.0, step=100.0, format="%.0f", key="feed_conc_price")
    with feed_col3:
        silo_price_t = st.number_input(
            "Цена силоса, за 1 т",
            value=200.0, step=10.0, format="%.1f", key="feed_silo_price")
        hay_price_t = st.number_input(
            "Цена сена, за 1 т",
            value=2000.0, step=100.0, format="%.0f", key="feed_hay_price")

    haylage_price_t = st.number_input(
        "Цена сенажа, за 1 т",
        value=500.0, step=50.0, format="%.0f", key="feed_haylage_price")

    # Проверка: нужны ли данные из анализа
    can_feed_calc = bool(silenta_extra and competitor_extra)
    if not can_feed_calc:
        st.info("⚠️ Для расчёта экономии на кормах нужно подтянуть параметры "
                "силосов из анализа (включите галочку выше и выберите "
                "образцы). Ручной ввод даёт только СВ% и ОЭ — этого "
                "недостаточно для расчёта рациона.")
    else:
        # Готовим параметры силосов для расчёта рациона
        silenta_silo = _sample_to_silo(silenta_extra)
        competitor_silo = _sample_to_silo(competitor_extra)

        try:
            feed_econ = calc_feed_economics(
                silenta_params=silenta_silo,
                competitor_params=competitor_silo,
                live_weight=live_weight_f,
                milk_yield=milk_yield_f,
                n_cows=int(n_cows),
                conc_price_per_t=conc_price_t,
                silo_price_per_t=silo_price_t,
                hay_price_per_t=hay_price_t,
                haylage_price_per_t=haylage_price_t,
            )

            # ---- Таблица расхода кормов на 1 корову ----
            st.markdown("#### Расход на 1 корову в день (кг нат. веса)")

            feed_table = pd.DataFrame([
                {"Корм": "Силос",
                 s_name: _fmt(feed_econ["silo1_nat"], 2),
                 c_name: _fmt(feed_econ["silo2_nat"], 2),
                 "Разница (эконом.)":
                     _fmt(feed_econ["delta_silo_nat"], 2)},
                {"Корм": "Комбикорм",
                 s_name: _fmt(feed_econ["conc1_nat"], 2),
                 c_name: _fmt(feed_econ["conc2_nat"], 2),
                 "Разница (эконом.)":
                     _fmt(feed_econ["delta_conc_nat"], 2)},
                {"Корм": "Сено",
                 s_name: _fmt(feed_econ["hay1_nat"], 2),
                 c_name: _fmt(feed_econ["hay2_nat"], 2),
                 "Разница (эконом.)":
                     _fmt(feed_econ["delta_hay_nat"], 2)},
                {"Корм": "Сенаж",
                 s_name: _fmt(feed_econ["haylage1_nat"], 2),
                 c_name: _fmt(feed_econ["haylage2_nat"], 2),
                 "Разница (эконом.)":
                     _fmt(feed_econ["delta_haylage_nat"], 2)},
            ])
            st.dataframe(feed_table, use_container_width=True, hide_index=True)

            # ---- Экономия на поголовье ----
            st.markdown(f"#### Экономия на поголовье ({n_cows} голов)")

            econ_rows = [
                {"Источник": "Силос",
                 "В день": _fmt(feed_econ["saving_silo_day"], 0),
                 "В год": _fmt(feed_econ["saving_silo_year"], 0)},
                {"Источник": "Комбикорм (концентраты)",
                 "В день": _fmt(feed_econ["saving_conc_day"], 0),
                 "В год": _fmt(feed_econ["saving_conc_year"], 0)},
                {"Источник": "Сено",
                 "В день": _fmt(feed_econ["saving_hay_day"], 0),
                 "В год": _fmt(feed_econ["saving_hay_year"], 0)},
                {"Источник": "Сенаж",
                 "В день": _fmt(feed_econ["saving_haylage_day"], 0),
                 "В год": _fmt(feed_econ["saving_haylage_year"], 0)},
                {"Источник": "**ИТОГО экономия на кормах**",
                 "В день": f"**{_fmt(feed_econ['total_feed_day'], 0)}**",
                 "В год": f"**{_fmt(feed_econ['total_feed_year'], 0)}**"},
            ]
            st.dataframe(pd.DataFrame(econ_rows),
                         use_container_width=True, hide_index=True)

            # ---- Метрики в день/год ----
            ec1, ec2, ec3, ec4 = st.columns(4)
            ec1.metric("Экономия на силосе, в день",
                        f"{_fmt(feed_econ['saving_silo_day'], 0)}")
            ec2.metric("Экономия на силосе, в год",
                        f"{_fmt(feed_econ['saving_silo_year'], 0)}")
            ec3.metric("Экономия на комбикорме, в день",
                        f"{_fmt(feed_econ['saving_conc_day'], 0)}")
            ec4.metric("Экономия на комбикорме, в год",
                        f"{_fmt(feed_econ['saving_conc_year'], 0)}")

            if feed_econ["total_feed_year"] > 0:
                st.success(
                    f"💰 **Общая экономия на кормах: "
                    f"{_fmt(feed_econ['total_feed_year'], 0)} в год** "
                    f"({_fmt(feed_econ['total_feed_day'], 0)} в день)."
                )
            elif feed_econ["total_feed_year"] < 0:
                st.warning(
                    f"⚠️ При текущих параметрах кормление силосом Сингенты "
                    f"дороже на {_fmt(abs(feed_econ['total_feed_year']), 0)} "
                    f"в год. Проверьте цены кормов."
                )

            # ---- Совокупная экономия ----
            st.markdown("#### Совокупная годовая экономия")
            grand_total = result["total_saving"] + feed_econ["total_feed_year"]

            grand_rows = [
                {"Источник": "Выращивание (за счёт урожайности и ОЭ)",
                 "В год": _fmt(result["total_saving"], 0)},
                {"Источник": "Кормление (силос + концентраты)",
                 "В год": _fmt(feed_econ["total_feed_year"], 0)},
                {"Источник": "**ИТОГО за год**",
                 "В год": f"**{_fmt(grand_total, 0)}**"},
            ]
            st.dataframe(pd.DataFrame(grand_rows),
                         use_container_width=True, hide_index=True)

            st.session_state["econ_feed_result"] = feed_econ
            st.session_state["econ_feed_params"] = {
                "live_weight": live_weight_f, "milk_yield": milk_yield_f,
                "n_cows": n_cows, "conc_price_t": conc_price_t,
                "silo_price_t": silo_price_t,
                "hay_price_t": hay_price_t,
                "haylage_price_t": haylage_price_t,
            }

            # ---- График экономии по источникам ----
            st.markdown("#### Структура экономии на кормах (в год)")
            fig_econ = go.Figure(data=[
                go.Bar(name="Силос", x=["Экономия"],
                       y=[feed_econ["saving_silo_year"]],
                       marker_color="#F39C12",
                       text=[_fmt(feed_econ["saving_silo_year"], 0)],
                       textposition="outside"),
                go.Bar(name="Комбикорм", x=["Экономия"],
                       y=[feed_econ["saving_conc_year"]],
                       marker_color="#3498DB",
                       text=[_fmt(feed_econ["saving_conc_year"], 0)],
                       textposition="outside"),
                go.Bar(name="Сено", x=["Экономия"],
                       y=[feed_econ["saving_hay_year"]],
                       marker_color="#8B4513",
                       text=[_fmt(feed_econ["saving_hay_year"], 0)],
                       textposition="outside"),
                go.Bar(name="Сенаж", x=["Экономия"],
                       y=[feed_econ["saving_haylage_year"]],
                       marker_color="#27AE60",
                       text=[_fmt(feed_econ["saving_haylage_year"], 0)],
                       textposition="outside"),
            ])
            fig_econ.update_layout(
                barmode="group", height=350, showlegend=True,
                margin=dict(l=10, r=10, t=30, b=10),
            )
            st.plotly_chart(fig_econ, use_container_width=True)

        except Exception as e:
            st.error(f"Ошибка расчёта экономии на кормах: {e}")

    # ================== ГРАФИКИ ВЫРАЩИВАНИЯ ==================
    st.markdown("---")
    st.subheader("6. Графики сравнения (выращивание)")
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
            go.Bar(name=s_name, x=["Затраты"], y=[s["total_cost"]],
                   marker_color="#2C7A3E", text=[_fmt(s["total_cost"], 0)],
                   textposition="outside"),
            go.Bar(name=c_name, x=["Затраты"], y=[c["total_cost"]],
                   marker_color="#7F8C8D", text=[_fmt(c["total_cost"], 0)],
                   textposition="outside"),
        ])
        fig_cost.update_layout(height=350, showlegend=True,
                                margin=dict(l=10, r=10, t=40, b=10),
                                title="Затраты на всю площадь")
        st.plotly_chart(fig_cost, use_container_width=True)

    # ================== AI-ВЫВОД ==================
    st.markdown("---")
    st.subheader("7. 🩺 Экономический вывод (ИИ)")

    col_a, col_b = st.columns([1, 4])
    with col_a:
        refresh_econ = st.button("🔄 Обновить", key="econ_ai_refresh")

    # Расширяем контекст, если есть расчёт кормов
    feed_context_extra = ""
    if "econ_feed_result" in st.session_state:
        fe = st.session_state["econ_feed_result"]
        feed_context_extra = (
            "\n\n=== ЭКОНОМИЯ НА КОРМАХ ===\n"
            f"Поголовье: {fe['n_cows']} голов\n"
            f"Экономия на силосе в год: "
            f"{fe['saving_silo_year']:,.0f}\n".replace(",", " ") +
            f"Экономия на комбикорме в год: "
            f"{fe['saving_conc_year']:,.0f}\n".replace(",", " ") +
            f"Общая экономия на кормах в год: "
            f"{fe['total_feed_year']:,.0f}\n".replace(",", " ")
        )

    econ_context = build_economics_context(
        result, s_name, c_name,
        silenta_extra=silenta_extra,
        competitor_extra=competitor_extra,
    ) + feed_context_extra

    with st.spinner("AI анализирует экономику..."):
        econ_ai_text = get_economics_ai_recommendation(
            econ_context, force_refresh=refresh_econ
        )

    st.markdown(econ_ai_text)

    # ================== PDF ==================
    st.markdown("---")
    st.subheader("8. 📄 PDF-отчёт")
    st.caption("Содержит: таблицу сравнения, лабораторные данные, "
               "экономию на выращивании, экономию на кормах, "
               "графики и вывод ИИ.")

    col_btn, col_dl = st.columns(2)
    with col_btn:
        if st.button("📄 Подготовить PDF-отчёт",
                      use_container_width=True, key="econ_pdf_prepare"):
            with st.spinner("Собираем PDF..."):
                try:
                    feed_econ_arg = st.session_state.get("econ_feed_result")
                    feed_params_arg = st.session_state.get("econ_feed_params")
                    pdf_bytes = generate_economics_pdf(
                        result=result,
                        silenta_name=s_name,
                        competitor_name=c_name,
                        silo_demand_t=silo_demand_t,
                        grain_price=grain_price,
                        ai_text=econ_ai_text,
                        silenta_extra=silenta_extra,
                        competitor_extra=competitor_extra,
                        feed_econ=feed_econ_arg,
                        feed_params=feed_params_arg,
                    )
                    st.session_state["econ_pdf_bytes"] = pdf_bytes
                    st.success("PDF готов! Нажмите кнопку справа.")
                except Exception as e:
                    st.error(f"Ошибка генерации PDF: {e}")

    with col_dl:
        if "econ_pdf_bytes" in st.session_state:
            st.download_button(
                "💾 Скачать PDF-отчёт",
                data=st.session_state["econ_pdf_bytes"],
                file_name="economics_report.pdf",
                mime="application/pdf",
                use_container_width=True,
                key="econ_pdf_download",
            )

    # ================== ИТОГ ==================
    st.markdown("---")
    st.info(
        "**Как считается экономия:**\n\n"
        "**Выращивание:** разница в ОЭ (МДж/га) → эквивалент зерна → "
        "экономия на зерне. Плюс — экономия затрат за счёт меньшей площади.\n\n"
        "**Кормление:** для каждой коровы считается рацион с двумя разными "
        "силосами. Разница в потреблении силоса и комбикорма × цены = "
        "экономия на 1 корову в день. × поголовье × 365 = экономия в год.\n\n"
        "**Все суммы — в одной валюте расчёта** (BYN, RUB, KZT и т.д.)."
    )
