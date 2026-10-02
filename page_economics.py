"""UI для страницы «Экономика выращивания» + экономия на кормах + PDF.
Два сценария: «фиксированная площадь» и «фиксированная потребность»."""

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


def _sample_to_silo(p: dict) -> dict:
    return {
        "DM": p["dm_pct"] * 10,
        "starch": p.get("starch") or 350,
        "sugar": p.get("sugar") or 0,
        "NDF": p.get("NDF") or 350,
        "ADF": p.get("ADF") or 180,
        "dOM": p.get("dOM") or 80,
        "NEL": p.get("NEL") or p["me"],
        "NEL_VC": p.get("NEL_VC") or p["me"],
        "nXP": p.get("nXP") or 135,
        "RNB": p.get("RNB") if p.get("RNB") is not None else -10,
        "structure": 1.5,
    }


def render_economics_page():
    st.header("💰 Экономика выращивания силосной кукурузы")
    st.caption("Сравнение двух гибридов и расчёт экономии. "
               "Все суммы — в валюте расчёта.")

    # ================== СЦЕНАРИЙ ==================
    st.subheader("0. Сценарий использования")
    scenario = st.radio(
        "Как вы планируете использовать землю?",
        [
            "📦 Мне нужно конкретное количество силоса (потребность)",
            "🌾 У меня есть фиксированная площадь",
        ],
        index=0,
        horizontal=False,
    )
    scenario_key = "demand" if "потребность" in scenario else "area"

    if scenario_key == "area":
        st.info("🌾 **Сценарий «Фиксированная площадь».** Оба гибрида "
                "засеиваются на одной площади. Более урожайный даёт "
                "излишек силоса, который можно продать или скормить.")
    else:
        st.info("📦 **Сценарий «Фиксированная потребность».** Нужно "
                "произвести конкретный объём силоса. Считаем, какой "
                "гибрид дешевле для этой цели.")

    # ================== ДАННЫЕ ИЗ АНАЛИЗА ==================
    analysis_records = st.session_state.get("analysis_df", [])
    has_analysis = bool(analysis_records)

    use_analysis = False
    if has_analysis:
        use_analysis = st.checkbox(
            f"🔬 Использовать данные из анализа кормов "
            f"(загружено {len(analysis_records)} образцов)",
            value=False,
        )
    else:
        st.info("💡 Данные анализа кормов не загружены. "
                "Перейдите на страницу «🌽 Анализ кормов» и загрузите файл.")

    def _options():
        return ["— ввести вручную —"] + [r.get("Образец", "—")
                                            for r in analysis_records]

    # ================== ОБЩИЕ ПАРАМЕТРЫ ==================
    st.subheader("1. Общие параметры")
    c1, c2 = st.columns(2)
    with c1:
        silo_demand_t = st.number_input(
            "Потребность в силосе, т/год",
            value=17_000.0, step=100.0, format="%.1f",
            help="В тоннах ЗМ. Внутри 1 т = 10 ц.")
    with c2:
        grain_price = st.number_input(
            "Цена кукурузного зерна, за 1 т (в валюте расчёта)",
            value=10_000.0, step=500.0, format="%.0f")

    silo_demand_c = silo_demand_t * 10

    # ================== ДВА ГИБРИДА ==================
    st.subheader("2. Параметры гибридов")
    col1, col2 = st.columns(2)

    silenta_extra = None
    competitor_extra = None

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
        else:
            s_dm = st.number_input("Содержание СВ, %",
                                     value=34.0, step=0.5, format="%.1f",
                                     key="econ_s_dm")
            s_me = st.number_input("ОЭ, МДж/кг СВ",
                                     value=10.8, step=0.1, format="%.2f",
                                     key="econ_s_me")

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
        else:
            c_dm = st.number_input("Содержание СВ, %",
                                     value=30.0, step=0.5, format="%.1f",
                                     key="econ_c_dm")
            c_me = st.number_input("ОЭ, МДж/кг СВ",
                                     value=10.4, step=0.1, format="%.2f",
                                     key="econ_c_me")

    # Площадь для сценария "area"
    fixed_area_ha = None
    if scenario_key == "area":
        # Автоматическая площадь = площадь конкурента для покрытия потребности
        auto_area = silo_demand_c / c_yield if c_yield > 0 else 0
        fixed_area_ha = st.number_input(
            "Фиксированная площадь, га",
            value=float(round(auto_area, 1)),
            step=10.0, format="%.1f",
            help="Площадь, на которой будут посеяны оба гибрида. "
                 "По умолчанию — площадь конкурента для покрытия потребности."
        )

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

    # ================== РАСЧЁТ ==================
    result = calculate_economics(
        silenta={"silo_demand": silo_demand_c, "yield_green": s_yield,
                  "seeding_rate": s_seed_rate, "seed_price": s_seed_price,
                  "field_cost": s_field_cost, "dm_pct": s_dm,
                  "me": s_me, "grain_price": grain_price},
        competitor={"silo_demand": silo_demand_c, "yield_green": c_yield,
                     "seeding_rate": c_seed_rate, "seed_price": c_seed_price,
                     "field_cost": c_field_cost, "dm_pct": c_dm,
                     "me": c_me, "grain_price": grain_price},
        scenario=scenario_key,
        fixed_area_ha=fixed_area_ha,
    )

    s = result["silenta"]
    c = result["competitor"]

    # ================== СВОДНАЯ ТАБЛИЦА ==================
    st.subheader("3. Сравнение гибридов")

    if scenario_key == "area":
        comparison = pd.DataFrame([
            {"Показатель": "Площадь, га",
             s_name: _fmt(result["same_area"], 1),
             c_name: _fmt(result["same_area"], 1)},
            {"Показатель": "Урожайность ЗМ, ц/га",
             s_name: _fmt(s_yield, 1), c_name: _fmt(c_yield, 1)},
            {"Показатель": "Содержание СВ, %",
             s_name: _fmt(s_dm, 1), c_name: _fmt(c_dm, 1)},
            {"Показатель": "Урожайность СВ, ц/га",
             s_name: _fmt(s["dm_yield"], 1), c_name: _fmt(c["dm_yield"], 1)},
            {"Показатель": "Валовый сбор СВ, ц",
             s_name: _fmt(s["dm_yield"] * result["same_area"], 0),
             c_name: _fmt(c["dm_yield"] * result["same_area"], 0)},
            {"Показатель": "Затраты на 1 га",
             s_name: _fmt(s["seed_cost_per_ha"] + s["field_cost"], 0),
             c_name: _fmt(c["seed_cost_per_ha"] + c["field_cost"], 0)},
            {"Показатель": "Затраты на всю площадь",
             s_name: _fmt(result["cost_silenta"], 0),
             c_name: _fmt(result["cost_competitor"], 0)},
            {"Показатель": "ОЭ, МДж/кг СВ",
             s_name: _fmt(s_me, 2), c_name: _fmt(c_me, 2)},
        ])
    else:
        comparison = pd.DataFrame([
            {"Показатель": "Площадь сева, га",
             s_name: _fmt(s["area"], 1), c_name: _fmt(c["area"], 1)},
            {"Показатель": "Урожайность ЗМ, ц/га",
             s_name: _fmt(s_yield, 1), c_name: _fmt(c_yield, 1)},
            {"Показатель": "Содержание СВ, %",
             s_name: _fmt(s_dm, 1), c_name: _fmt(c_dm, 1)},
            {"Показатель": "Урожайность СВ, ц/га",
             s_name: _fmt(s["dm_yield"], 1), c_name: _fmt(c["dm_yield"], 1)},
            {"Показатель": "Валовый сбор СВ, ц",
             s_name: _fmt(s["dm_total"], 0), c_name: _fmt(c["dm_total"], 0)},
            {"Показатель": "Затраты на 1 га",
             s_name: _fmt(s["seed_cost_per_ha"] + s["field_cost"], 0),
             c_name: _fmt(c["seed_cost_per_ha"] + c["field_cost"], 0)},
            {"Показатель": "Затраты на всю площадь",
             s_name: _fmt(s["total_cost"], 0),
             c_name: _fmt(c["total_cost"], 0)},
            {"Показатель": "ОЭ, МДж/кг СВ",
             s_name: _fmt(s_me, 2), c_name: _fmt(c_me, 2)},
        ])
    st.dataframe(comparison, use_container_width=True, hide_index=True)

    # ================== ЭКОНОМИЯ НА ВЫРАЩИВАНИИ ==================
    st.subheader("4. Экономия на выращивании")

    if scenario_key == "area":
        st.caption("Оба гибрида засеяны на одной площади. Сравниваем затраты "
                   "и стоимость излишка у более урожайного.")

        ea, eb, ec = st.columns(3)
        ea.metric(f"Затраты — {s_name}",
                   f"{_fmt(result['cost_silenta'], 0)}")
        eb.metric(f"Затраты — {c_name}",
                   f"{_fmt(result['cost_competitor'], 0)}")
        ec.metric("Экономия затрат",
                   f"{_fmt(result['saving_field'], 0)}")

        st.markdown("---")
        st.markdown("#### Излишек силоса")
        st.caption(f"**{s_name}** на той же площади даёт больше силоса. "
                   "Этот излишек можно продать или использовать как замену "
                   "покупного зерна.")

        sm1, sm2, sm3 = st.columns(3)
        sm1.metric("Излишек СВ",
                    f"{_fmt(result['surplus_dm_t'], 1)} т СВ")
        sm2.metric("Излишек ЗМ (силоса)",
                    f"{_fmt(result['surplus_gm_t'], 1)} т ЗМ")
        sm3.metric("Эквивалент зерна по ОЭ",
                    f"{_fmt(result['surplus_grain_t'], 1)} т зерна")

        st.markdown("**Как оценить излишек?** Выберите вариант:")
        val_type = st.radio(
            "Метод оценки излишка:",
            [
                "💰 Как продажа силоса (по цене силоса за 1 т ЗМ)",
                "🌾 Как замена покупного зерна (по цене зерна за 1 т)",
            ],
            key="surplus_val_type",
            horizontal=False,
        )

        if "продажа" in val_type.lower():
            silo_price_surplus = st.number_input(
                "Цена силоса за 1 т ЗМ",
                value=200.0, step=10.0, format="%.1f",
                key="surplus_silo_price")
            surplus_value = result["surplus_gm_t"] * silo_price_surplus
            surplus_note = (f"{_fmt(result['surplus_gm_t'], 1)} т ЗМ × "
                            f"{_fmt(silo_price_surplus, 0)} = "
                            f"**{_fmt(surplus_value, 0)}**")
        else:
            surplus_value = result["surplus_grain_t"] * grain_price
            surplus_note = (f"{_fmt(result['surplus_grain_t'], 1)} т зерна × "
                            f"{_fmt(grain_price, 0)} = "
                            f"**{_fmt(surplus_value, 0)}**")

        st.info(f"**Оценка излишка:** {surplus_note}")

        total_field_saving = result["saving_field"] + surplus_value
        st.metric("💰 Итого по выращиванию",
                   f"{_fmt(total_field_saving, 0)}")
        st.session_state["_econ_field_total"] = total_field_saving
    else:
        st.caption("Площади подобраны так, чтобы получить нужный объём силоса.")

        ea, eb, ec, ed = st.columns(4)
        ea.metric(f"Площадь — {s_name}",
                   f"{_fmt(result['silenta_area'], 1)} га")
        eb.metric(f"Площадь — {c_name}",
                   f"{_fmt(result['competitor_area'], 1)} га")
        ec.metric("Освобождено площади",
                   f"{_fmt(result['freed_area'], 1)} га")
        ed.metric("Экономия затрат",
                   f"{_fmt(result['saving_field'], 0)}")

        st.metric("💰 Итого по выращиванию",
                   f"{_fmt(result['saving_field'], 0)}")
        st.session_state["_econ_field_total"] = result["saving_field"]

        st.caption(
            f"**{s_name}** требует меньше площади для покрытия потребности "
            f"({_fmt(result['silenta_area'], 1)} га против "
            f"{_fmt(result['competitor_area'], 1)} га), но затраты на 1 га "
            f"у него выше из-за стоимости семян."
        )

    # ================== ЭКОНОМИЯ НА КОРМАХ ==================
    st.markdown("---")
    st.subheader("5. Экономия на кормах (для заданного удоя)")
    st.caption("Сколько силоса и комбикорма нужно каждой корове при "
               "использовании силоса Сингенты vs конкурента.")

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

    can_feed_calc = bool(silenta_extra and competitor_extra)
    if not can_feed_calc:
        st.info("⚠️ Для расчёта экономии на кормах нужно подтянуть параметры "
                "силосов из анализа (включите галочку выше и выберите "
                "образцы).")
    else:
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

            st.markdown("#### Расход на 1 корову в день (кг нат. веса)")
            feed_table = pd.DataFrame([
                {"Корм": "Силос",
                 s_name: _fmt(feed_econ["silo1_nat"], 2),
                 c_name: _fmt(feed_econ["silo2_nat"], 2),
                 "Разница": _fmt(feed_econ["delta_silo_nat"], 2)},
                {"Корм": "Комбикорм",
                 s_name: _fmt(feed_econ["conc1_nat"], 2),
                 c_name: _fmt(feed_econ["conc2_nat"], 2),
                 "Разница": _fmt(feed_econ["delta_conc_nat"], 2)},
                {"Корм": "Сено",
                 s_name: _fmt(feed_econ["hay1_nat"], 2),
                 c_name: _fmt(feed_econ["hay2_nat"], 2),
                 "Разница": _fmt(feed_econ["delta_hay_nat"], 2)},
                {"Корм": "Сенаж",
                 s_name: _fmt(feed_econ["haylage1_nat"], 2),
                 c_name: _fmt(feed_econ["haylage2_nat"], 2),
                 "Разница": _fmt(feed_econ["delta_haylage_nat"], 2)},
            ])
            st.dataframe(feed_table, use_container_width=True, hide_index=True)
            st.caption("Отрицательная разница по силосу перекрывается "
                       "экономией на комбикорме.")

            st.markdown(f"#### Экономия на поголовье ({n_cows} голов)")
            econ_rows = [
                {"Источник": "Силос",
                 "В день": _fmt(feed_econ["saving_silo_day"], 0),
                 "В год": _fmt(feed_econ["saving_silo_year"], 0)},
                {"Источник": "Комбикорм",
                 "В день": _fmt(feed_econ["saving_conc_day"], 0),
                 "В год": _fmt(feed_econ["saving_conc_year"], 0)},
                {"Источник": "Сено",
                 "В день": _fmt(feed_econ["saving_hay_day"], 0),
                 "В год": _fmt(feed_econ["saving_hay_year"], 0)},
                {"Источник": "Сенаж",
                 "В день": _fmt(feed_econ["saving_haylage_day"], 0),
                 "В год": _fmt(feed_econ["saving_haylage_year"], 0)},
                {"Источник": "**ИТОГО**",
                 "В день": f"**{_fmt(feed_econ['total_feed_day'], 0)}**",
                 "В год": f"**{_fmt(feed_econ['total_feed_year'], 0)}**"},
            ]
            st.dataframe(pd.DataFrame(econ_rows),
                         use_container_width=True, hide_index=True)

            st.session_state["econ_feed_result"] = feed_econ
            st.session_state["econ_feed_params"] = {
                "live_weight": live_weight_f, "milk_yield": milk_yield_f,
                "n_cows": n_cows, "conc_price_t": conc_price_t,
                "silo_price_t": silo_price_t,
                "hay_price_t": hay_price_t,
                "haylage_price_t": haylage_price_t,
            }
        except Exception as e:
            st.error(f"Ошибка расчёта экономии на кормах: {e}")

    # ================== СОВОКУПНАЯ ЭКОНОМИЯ ==================
    st.markdown("---")
    st.subheader("6. Совокупная годовая экономия")

    field_total = st.session_state.get("_econ_field_total", 0)
    feed_total = 0
    if "econ_feed_result" in st.session_state:
        feed_total = st.session_state["econ_feed_result"]["total_feed_year"]

    grand = field_total + feed_total

    rows = [
        {"Источник": "Выращивание", "В год": _fmt(field_total, 0)},
    ]
    if feed_total:
        rows.append({"Источник": "Кормление", "В год": _fmt(feed_total, 0)})
    rows.append({"Источник": "**ИТОГО за год**", "В год": f"**{_fmt(grand, 0)}**"})

    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if grand > 0:
        st.success(f"💰 Совокупная годовая экономия: **{_fmt(grand, 0)}**.")
    elif grand < 0:
        st.error(f"При текущих параметрах **{c_name}** выгоднее на "
                 f"**{_fmt(abs(grand), 0)}**.")

    st.session_state["econ_scenario"] = scenario_key
    st.session_state["econ_result"] = result
    st.session_state["econ_grand"] = grand

    # ================== ГРАФИКИ ==================
    st.subheader("7. Графики")
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
        if scenario_key == "area":
            cost_s = result["cost_silenta"]
            cost_c = result["cost_competitor"]
            title = f"Затраты на {_fmt(result['same_area'], 1)} га"
        else:
            cost_s = s["total_cost"]
            cost_c = c["total_cost"]
            title = "Затраты на всю площадь"

        fig_cost = go.Figure(data=[
            go.Bar(name=s_name, x=["Затраты"], y=[cost_s],
                   marker_color="#2C7A3E", text=[_fmt(cost_s, 0)],
                   textposition="outside"),
            go.Bar(name=c_name, x=["Затраты"], y=[cost_c],
                   marker_color="#7F8C8D", text=[_fmt(cost_c, 0)],
                   textposition="outside"),
        ])
        fig_cost.update_layout(height=350, showlegend=True,
                                margin=dict(l=10, r=10, t=40, b=10),
                                title=title)
        st.plotly_chart(fig_cost, use_container_width=True)

    # ================== AI-ВЫВОД ==================
    st.markdown("---")
    st.subheader("8. 🩺 Экономический вывод")

    col_a, col_b = st.columns([1, 4])
    with col_a:
        refresh_econ = st.button("🔄 Обновить", key="econ_ai_refresh")

    feed_context_extra = f"\n=== СЦЕНАРИЙ ===\n{scenario}\n"
    if "econ_feed_result" in st.session_state:
        fe = st.session_state["econ_feed_result"]
        feed_context_extra += (
            f"\n=== ЭКОНОМИЯ НА КОРМАХ ===\n"
            f"Поголовье: {fe['n_cows']} голов\n"
            f"Экономия на силосе в год: {fe['saving_silo_year']:,.0f}\n"
            .replace(",", " ") +
            f"Экономия на комбикорме в год: {fe['saving_conc_year']:,.0f}\n"
            .replace(",", " ") +
            f"Общая экономия на кормах в год: {fe['total_feed_year']:,.0f}\n"
            .replace(",", " ")
        )

    econ_context = build_economics_context(
        result, s_name, c_name,
        silenta_extra=silenta_extra,
        competitor_extra=competitor_extra,
    ) + feed_context_extra

    with st.spinner("Анализируем экономику..."):
        econ_ai_text = get_economics_ai_recommendation(
            econ_context, force_refresh=refresh_econ
        )

    st.markdown(econ_ai_text)

    # ================== PDF ==================
    st.markdown("---")
    st.subheader("9. 📄 PDF-отчёт")

    col_btn, col_dl = st.columns(2)
    with col_btn:
        if st.button("📄 Подготовить PDF-отчёт",
                      use_container_width=True, key="econ_pdf_prepare"):
            with st.spinner("Собираем PDF..."):
                try:
                    pdf_bytes = generate_economics_pdf(
                        result=result,
                        silenta_name=s_name,
                        competitor_name=c_name,
                        silo_demand_t=silo_demand_t,
                        grain_price=grain_price,
                        ai_text=econ_ai_text,
                        silenta_extra=silenta_extra,
                        competitor_extra=competitor_extra,
                        feed_econ=st.session_state.get("econ_feed_result"),
                        feed_params=st.session_state.get("econ_feed_params"),
                        total_grand=grand,
                        scenario=scenario_key,
                        surplus_value=st.session_state.get(
                            "_econ_field_total", 0) - result["saving_field"],
                    )
                    st.session_state["econ_pdf_bytes"] = pdf_bytes
                    st.success("PDF готов!")
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
