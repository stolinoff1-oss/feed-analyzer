"""UI для страницы «Экономика выращивания» + экономия на кормах + PDF."""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from economics import (calculate_economics, calc_feed_economics,
                        calc_silo_surplus)
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
    st.caption("Сравнение двух гибридов и расчёт экономии — при выращивании "
               "и при кормлении. Все суммы — в валюте расчёта.")

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
                "Перейдите на страницу «🌽 Анализ кормов» и загрузите файл.")

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
            help="В тоннах ЗМ. Внутри 1 т = 10 ц.")
    with c2:
        grain_price = st.number_input(
            "Цена кукурузного зерна, за 1 т (в валюте расчёта)",
            value=10_000.0, step=500.0, format="%.0f")

    silo_demand_c = silo_demand_t * 10

    # ================== ДВА ГИБРИДА ==================
    st.subheader("2. Параметры гибридов (силосов)")
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
            st.caption("🔒 Значения подтянуты из анализа.")
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
    total_col2.metric("💰 Экономия на выращивании (в год)",
                       f"{_fmt(result['total_saving'], 0)}")

    if result["total_saving"] > 0:
        st.success(
            f"**{s_name}** обеспечивает экономию на выращивании "
            f"**{_fmt(result['total_saving'], 0)}** "
            f"({_fmt(result['total_saving_per_ha'], 0)} /га).")
    elif result["total_saving"] < 0:
        st.error(f"При текущих параметрах **{s_name}** проигрывает "
                 f"**{c_name}** на {_fmt(abs(result['total_saving']), 0)}.")

    # ================== ИЗЛИШЕК СИЛОСА ==================
    st.markdown("---")
    st.subheader("4.1. Излишек силоса при одинаковой площади")
    st.caption("Если засеять одинаковую площадь (по площади конкурента), "
               "урожайный гибрид даст больше силоса. Этот излишек можно "
               "продать или скормить — это чистая дополнительная выгода.")

    show_surplus = st.checkbox(
        "Учитывать излишек силоса",
        value=True,
        key="show_surplus",
    )

    if show_surplus:
        sc1, sc2 = st.columns(2)
        with sc1:
            silo_price_surplus = st.number_input(
                "Цена силоса за 1 т ЗМ (для продажи)",
                value=200.0, step=10.0, format="%.1f",
                key="surplus_silo_price",
                help="Сколько стоит 1 тонна готового силоса (ЗМ)")
        with sc2:
            st.metric("Одинаковая площадь (по конкуренту)",
                       f"{_fmt(c['area'], 1)} га")

        surplus = calc_silo_surplus(
            silenta_result=s,
            competitor_result=c,
            silo_price_per_t=silo_price_surplus,
            grain_price=grain_price,
        )

        sm1, sm2, sm3 = st.columns(3)
        sm1.metric("Излишек СВ", f"{_fmt(surplus['surplus_dm_t'], 1)} т СВ")
        sm2.metric("Излишек ЗМ", f"{_fmt(surplus['surplus_gm_t'], 1)} т ЗМ")
        sm3.metric("Эквивалент зерна",
                    f"{_fmt(surplus['surplus_grain_t'], 1)} т зерна")

        st.markdown("**Оценка стоимости излишка (два варианта):**")
        ev1, ev2 = st.columns(2)
        ev1.metric("💰 Продажа силоса",
                    f"{_fmt(surplus['saving_sale'], 0)}")
        ev2.metric("💰 Как замена зерна по ОЭ",
                    f"{_fmt(surplus['saving_grain_equiv'], 0)}")

        st.info(
            f"**Пояснение.** Если оба гибрида засеять на "
            f"{_fmt(c['area'], 1)} га, то {s_name} даст на "
            f"**{_fmt(surplus['surplus_dm_t'], 1)} т СВ** больше. Это:\n\n"
            f"• **Продажа силоса:** {_fmt(surplus['surplus_gm_t'], 1)} т ЗМ × "
            f"{_fmt(silo_price_surplus, 0)} = "
            f"**{_fmt(surplus['saving_sale'], 0)}**\n\n"
            f"• **Как замена зерна:** излишек содержит "
            f"{_fmt(surplus['surplus_me_mj'], 0)} МДж ОЭ = "
            f"{_fmt(surplus['surplus_grain_t'], 1)} т зерна × "
            f"{_fmt(grain_price, 0)} = "
            f"**{_fmt(surplus['saving_grain_equiv'], 0)}**\n\n"
            f"Разница между оценками в том, что силос и зерно не полностью "
            f"взаимозаменяемы — силос даёт объёмистость, зерно — концентрацию."
        )

        st.session_state["econ_surplus"] = surplus
        st.session_state["econ_surplus_price"] = silo_price_surplus
    else:
        st.session_state.pop("econ_surplus", None)

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
                       "экономией на комбикорме в несколько раз.")

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

    grand = result["total_saving"]
    rows = [
        {"Источник": "Выращивание (урожайность + ОЭ)",
         "В год": _fmt(result["total_saving"], 0)},
    ]
    if "econ_feed_result" in st.session_state:
        fe = st.session_state["econ_feed_result"]
        grand += fe["total_feed_year"]
        rows.append({"Источник": "Кормление (силос + концентраты)",
                     "В год": _fmt(fe["total_feed_year"], 0)})
    if "econ_surplus" in st.session_state:
        sp = st.session_state["econ_surplus"]
        grand += sp["saving_sale"]
        rows.append({"Источник": "Излишек силоса (продажа)",
                     "В год": _fmt(sp["saving_sale"], 0)})
    rows.append({"Источник": "**ИТОГО за год**",
                 "В год": f"**{_fmt(grand, 0)}**"})

    st.dataframe(pd.DataFrame(rows),
                 use_container_width=True, hide_index=True)

    if grand > 0:
        st.success(f"💰 Совокупная годовая экономия: **{_fmt(grand, 0)}**.")

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
    st.subheader("8. 🩺 Экономический вывод (ИИ)")

    col_a, col_b = st.columns([1, 4])
    with col_a:
        refresh_econ = st.button("🔄 Обновить", key="econ_ai_refresh")

    feed_context_extra = ""
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
    if "econ_surplus" in st.session_state:
        sp = st.session_state["econ_surplus"]
        feed_context_extra += (
            f"\n=== ИЗЛИШЕК СИЛОСА ===\n"
            f"При одинаковой площади ({sp['same_area']:.1f} га) излишек:\n"
            f"{sp['surplus_dm_t']:.1f} т СВ = {sp['surplus_gm_t']:.1f} т ЗМ\n"
            f"Продажа: {sp['saving_sale']:,.0f}\n".replace(",", " ")
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
                        surplus=st.session_state.get("econ_surplus"),
                        total_grand=grand,
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
