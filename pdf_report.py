import io
import os
import datetime
import re
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# --- Шрифты с кириллицей из matplotlib ---
_MPL_FONTS = os.path.join(matplotlib.get_data_path(), "fonts", "ttf")
_REGULAR = os.path.join(_MPL_FONTS, "DejaVuSans.ttf")
_BOLD = os.path.join(_MPL_FONTS, "DejaVuSans-Bold.ttf")

pdfmetrics.registerFont(TTFont("DejaVu", _REGULAR))
pdfmetrics.registerFont(TTFont("DejaVu-Bold", _BOLD))
pdfmetrics.registerFontFamily("DejaVu", normal="DejaVu", bold="DejaVu-Bold")

PRIMARY = colors.HexColor("#2C7A3E")
ACCENT = colors.HexColor("#F39C12")
GREY = colors.HexColor("#7F8C8D")
LIGHT = colors.HexColor("#ECF0F1")


# =============== ГРАФИКИ ===============

def _bar_chart(labels, values, title, color="#2C7A3E", highlight_top=True):
    fig, ax = plt.subplots(figsize=(7.5, max(2.5, len(labels) * 0.45)))
    color_list = [color] * len(labels)
    if highlight_top and values:
        max_v = max(values)
        color_list = ["#27AE60" if v == max_v else color for v in values]
    y_pos = list(range(len(labels)))
    bars = ax.barh(y_pos, values, color=color_list)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=9)
    ax.invert_yaxis()
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.grid(axis="x", linestyle="--", alpha=0.3)
    for bar, v in zip(bars, values):
        ax.text(bar.get_width(), bar.get_y() + bar.get_height() / 2,
                f" {v:.2f}", va="center", fontsize=8)
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    buf.seek(0)
    return buf


def _grouped_chart(labels, series: dict, title):
    fig, ax = plt.subplots(figsize=(7.5, 3.5))
    x = np.arange(len(labels))
    width = 0.8 / len(series)
    palette = ["#F39C12", "#E74C3C", "#27AE60", "#3498DB"]
    for i, (name, values) in enumerate(series.items()):
        ax.bar(x + i * width, values, width=width, label=name,
               color=palette[i % len(palette)])
    ax.set_xticks(x + width * (len(series) - 1) / 2)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.grid(axis="y", linestyle="--", alpha=0.3)
    ax.legend(fontsize=8)
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    buf.seek(0)
    return buf


def _radar_chart(df: pd.DataFrame, top_n: int = 4):
    params = [
        ("NEL-VC", "NEL-VC", True),
        ("СП", "СП, г/кг", True),
        ("Крахмал", "Крахмал", True),
        ("Сахар", "Сахар", True),
        ("Перев. ОВ", "Перев. ОВ, %", True),
        ("Низкий НДК", "НДК", False),
    ]
    labels = [p[0] for p in params]
    data = []
    for _, col, higher in params:
        vals = pd.to_numeric(df[col], errors="coerce").fillna(0)
        if higher:
            score = (vals - vals.min()) / (vals.max() - vals.min() + 1e-9) * 100
        else:
            score = (vals.max() - vals) / (vals.max() - vals.min() + 1e-9) * 100
        data.append(score.tolist())

    angles = np.linspace(0, 2 * np.pi, len(labels), endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(6, 5), subplot_kw=dict(polar=True))
    palette = ["#27AE60", "#3498DB", "#F39C12", "#E74C3C"]
    for i, (_, row) in enumerate(df.head(top_n).iterrows()):
        values = [data[j][i] for j in range(len(labels))] + [data[0][i]]
        ax.plot(angles, values, label=row["Образец"],
                color=palette[i % len(palette)], linewidth=2)
        ax.fill(angles, values, color=palette[i % len(palette)], alpha=0.15)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylim(0, 100)
    ax.set_title("Профиль образцов", fontsize=11, fontweight="bold", pad=15)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=8)
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=120)
    plt.close(fig)
    buf.seek(0)
    return buf


# =============== MARKDOWN → REPORTLAB ===============

def _inline_md(s: str) -> str:
    s = s.replace("&", "&amp;")
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<i>\1</i>", s)
    return s


def _md_to_story(text: str, styles):
    story = []
    for line in text.split("\n"):
        line = line.rstrip()
        if not line:
            story.append(Spacer(1, 3))
            continue
        if line.startswith("### "):
            story.append(Paragraph(_inline_md(line[4:]), styles["h3"]))
            continue
        if line.startswith("## "):
            story.append(Paragraph(_inline_md(line[3:]), styles["h2"]))
            continue
        if line.startswith("# "):
            story.append(Paragraph(_inline_md(line[2:]), styles["h1"]))
            continue
        if line.startswith("  - ") or line.startswith("  • "):
            story.append(Paragraph(f"&nbsp;&nbsp;&nbsp;◦ {_inline_md(line[4:].lstrip('-• '))}",
                                    styles["bullet2"]))
            continue
        if line.startswith("- ") or line.startswith("* "):
            story.append(Paragraph(f"• {_inline_md(line[2:])}", styles["bullet"]))
            continue
        m = re.match(r"^(\d+)\.\s+(.*)$", line)
        if m:
            story.append(Paragraph(f"{m.group(1)}. {_inline_md(m.group(2))}",
                                    styles["bullet"]))
            continue
        if line.startswith("|") and line.endswith("|"):
            if re.match(r"^\|[\s\-:|]+\|$", line):
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            story.append(Paragraph(
                " &nbsp;|&nbsp; ".join(_inline_md(c) for c in cells),
                styles["table_row"]))
            continue
        story.append(Paragraph(_inline_md(line), styles["body"]))
    return story


# =============== СБОРКА PDF ===============

def generate_pdf(analysis: dict, rations: dict, ai_text: str,
                 live_weight: float, milk_yield: float) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=15 * mm, bottomMargin=15 * mm,
        title="Отчёт по анализу кормов",
        author="Feed Analyzer",
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("Title2", parent=styles["Title"],
                              fontName="DejaVu-Bold", fontSize=20,
                              textColor=PRIMARY, spaceAfter=8))
    styles.add(ParagraphStyle("h1", parent=styles["Heading1"],
                              fontName="DejaVu-Bold", fontSize=15,
                              textColor=PRIMARY, spaceAfter=6, spaceBefore=10))
    styles.add(ParagraphStyle("h2", parent=styles["Heading2"],
                              fontName="DejaVu-Bold", fontSize=12,
                              textColor=colors.HexColor("#1F4E2C"),
                              spaceAfter=4, spaceBefore=8))
    styles.add(ParagraphStyle("h3", parent=styles["Heading3"],
                              fontName="DejaVu-Bold", fontSize=11,
                              textColor=colors.HexColor("#2C7A3E"),
                              spaceAfter=2, spaceBefore=6))
    styles.add(ParagraphStyle("body", parent=styles["BodyText"],
                              fontName="DejaVu", fontSize=10, leading=14))
    styles.add(ParagraphStyle("bullet", parent=styles["BodyText"],
                              fontName="DejaVu", fontSize=10, leading=14,
                              leftIndent=12))
    styles.add(ParagraphStyle("bullet2", parent=styles["BodyText"],
                              fontName="DejaVu", fontSize=9, leading=13,
                              leftIndent=24))
    styles.add(ParagraphStyle("small", parent=styles["BodyText"],
                              fontName="DejaVu", fontSize=8,
                              textColor=GREY, leading=11))
    styles.add(ParagraphStyle("table_row", parent=styles["BodyText"],
                              fontName="DejaVu", fontSize=9, leading=12))

    story = []
    date_str = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")

    # ---- Титул ----
    story.append(Paragraph("Отчёт по анализу кормов", styles["Title2"]))
    story.append(Paragraph(f"Сформирован: {date_str}", styles["small"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"<b>Параметры коровы:</b> живая масса {live_weight} кг, "
        f"суточный удой {milk_yield} кг", styles["body"]))
    story.append(Paragraph(
        f"<b>Проанализировано образцов:</b> {len(analysis['ratings'])}",
        styles["body"]))
    story.append(Spacer(1, 10))

    # ---- 1. Сводная таблица ----
    story.append(Paragraph("1. Сводная таблица образцов", styles["h1"]))
    summary_data = [["№", "Образец", "Балл", "NEL-VC",
                     "СП", "Крахмал", "НДК", "RNB"]]
    for i, s in enumerate(analysis["ratings"], 1):
        summary_data.append([
            str(i), str(s["name"])[:22],
            f"{s['score']:.1f}" if s["score"] is not None else "—",
            f"{s['NEL_VC']:.2f}" if s["NEL_VC"] is not None else "—",
            f"{s['CP']:.0f}" if s["CP"] is not None else "—",
            f"{s['starch']:.0f}" if s["starch"] is not None else "—",
            f"{s['NDF']:.0f}" if s["NDF"] is not None else "—",
            f"{s['RNB']:.1f}" if s["RNB"] is not None else "—",
        ])
    t = Table(summary_data, colWidths=[10*mm, 42*mm, 15*mm, 18*mm,
                                        14*mm, 20*mm, 14*mm, 17*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "DejaVu-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "DejaVu"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.3, GREY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(PageBreak())

    # ---- 2. Графики ----
    story.append(Paragraph("2. Графики сравнения", styles["h1"]))

    df = pd.DataFrame([{
        "Образец": s["name"],
        "Балл": s["score"] or 0,
        "NEL-VC": s["NEL_VC"] or 0,
        "СП, г/кг": s["CP"] or 0,
        "Крахмал": s["starch"] or 0,
        "Сахар": s["sugar"] or 0,
        "НДК": s["NDF"] or 0,
        "Перев. ОВ, %": s["dOM"] or 0,
        "RNB": s["RNB"] or 0,
    } for s in analysis["ratings"]])

    story.append(Paragraph("2.1 Рейтинг образцов", styles["h2"]))
    story.append(Image(_bar_chart(df["Образец"].tolist(),
                                    df["Балл"].tolist(),
                                    "Рейтинг по баллу качества"),
                        width=170*mm, height=75*mm))

    story.append(Paragraph("2.2 Энергия: NEL-VC", styles["h2"]))
    df_nel = df.sort_values("NEL-VC", ascending=False)
    story.append(Image(_bar_chart(df_nel["Образец"].tolist(),
                                    df_nel["NEL-VC"].tolist(),
                                    "NEL-VC (МДж/кг СВ)", color="#3498DB"),
                        width=170*mm, height=75*mm))

    story.append(Paragraph("2.3 Сырой протеин", styles["h2"]))
    df_cp = df.sort_values("СП, г/кг", ascending=False)
    story.append(Image(_bar_chart(df_cp["Образец"].tolist(),
                                    df_cp["СП, г/кг"].tolist(),
                                    "СП (г/кг СВ)", color="#27AE60"),
                        width=170*mm, height=75*mm))
    story.append(PageBreak())

    story.append(Paragraph("2.4 Углеводный баланс", styles["h2"]))
    story.append(Image(_grouped_chart(
        df["Образец"].tolist(),
        {"Крахмал": df["Крахмал"].tolist(),
         "Сахар": df["Сахар"].tolist(),
         "НДК": df["НДК"].tolist()},
        "Крахмал, сахар, НДК"), width=170*mm, height=85*mm))

    story.append(Paragraph("2.5 Профиль образцов (радар)", styles["h2"]))
    try:
        story.append(Image(_radar_chart(df, top_n=4),
                            width=145*mm, height=120*mm))
    except Exception:
        story.append(Paragraph("Радар не построен.", styles["small"]))
    story.append(PageBreak())

    # ---- 3. Рационы ----
    story.append(Paragraph("3. Расчёт рационов для всех образцов",
                            styles["h1"]))

    for i, (name, r) in enumerate(rations.items(), 1):
        story.append(Paragraph(f"3.{i}. {name}", styles["h2"]))

        norm = r["norms"]
        tot = r["total"]
        metrics = [
            ["Показатель", "Норма", "Факт", "Разница"],
            ["NEL, МДж", f"{norm['NEL']}", f"{tot['NEL']:.1f}",
             f"{tot['NEL'] - norm['NEL']:+.1f}"],
            ["nXP, г", f"{norm['nXP']}", f"{tot['nXP']:.0f}",
             f"{tot['nXP'] - norm['nXP']:+.0f}"],
            ["СВ, кг", f"{norm['DM']}", f"{tot['dm']:.2f}",
             f"{tot['dm'] - norm['DM']:+.2f}"],
            ["НДК, г", "—", f"{tot['NDF']:.0f}",
             f"{100 * tot['NDF'] / (tot['dm'] * 1000):.1f}% СВ"],
        ]
        t1 = Table(metrics, colWidths=[42*mm, 28*mm, 28*mm, 42*mm])
        t1.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "DejaVu-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "DejaVu"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.3, GREY),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t1)
        story.append(Spacer(1, 5))

        comp = [["Корм", "СВ, кг", "Нат. вес, кг",
                 "NEL, МДж", "nXP, г", "НДК, г"]]
        for feed, vals in r["ration"].items():
            comp.append([feed, f"{vals['dm']:.2f}", f"{vals['nat']:.2f}",
                         f"{vals['NEL']:.1f}", f"{vals['nXP']:.0f}",
                         f"{vals['NDF']:.0f}"])
        t2 = Table(comp, colWidths=[52*mm, 20*mm, 28*mm,
                                      24*mm, 20*mm, 22*mm])
        t2.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "DejaVu-Bold"),
            ("FONTNAME", (0, 1), (-1, -1), "DejaVu"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("ALIGN", (1, 0), (-1, -1), "CENTER"),
            ("GRID", (0, 0), (-1, -1), 0.3, GREY),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t2)

        if r["corrections"]:
            story.append(Spacer(1, 4))
            story.append(Paragraph("<b>Корректировки:</b>", styles["body"]))
            for c in r["corrections"]:
                story.append(Paragraph(f"• {c}", styles["bullet"]))

        story.append(Spacer(1, 12))

    story.append(PageBreak())

    # ---- 4. Выводы AI ----
    story.append(Paragraph("4. Выводы зоотехника (ИИ)", styles["h1"]))
    story.append(Spacer(1, 4))
    story.extend(_md_to_story(ai_text, styles))

    story.append(Spacer(1, 20))
    story.append(Paragraph(
        f"Отчёт сформирован автоматически • {date_str} • Feed Analyzer",
        styles["small"]))

    doc.build(story)
    buffer.seek(0)
    return buffer.getvalue()
