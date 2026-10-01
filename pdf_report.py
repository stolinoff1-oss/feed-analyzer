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
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Image, PageBreak,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


CONTACT_EMAIL = "viktar.hrechka@syngenta.com"
CONTACT_TEXT = f"По всем вопросам: {CONTACT_EMAIL}"


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
BORDER = colors.HexColor("#D5DBDB")


# =============== КОЛОНТИТУЛЫ ===============

def _draw_page_decorations(canvas, doc):
    canvas.saveState()
    page_w, page_h = A4
    logo_height = 9 * mm
    top_pad = 8 * mm
    side_pad = 15 * mm

    if os.path.exists("logo1.png"):
        try:
            img = ImageReader("logo1.png")
            iw, ih = img.getSize()
            w = logo_height * iw / ih
            canvas.drawImage("logo1.png", side_pad,
                              page_h - top_pad - logo_height,
                              width=w, height=logo_height,
                              preserveAspectRatio=True, mask="auto")
        except Exception:
            pass

    if os.path.exists("logo3.png"):
        try:
            img = ImageReader("logo3.png")
            iw, ih = img.getSize()
            w = logo_height * iw / ih
            canvas.drawImage("logo3.png", page_w - side_pad - w,
                              page_h - top_pad - logo_height,
                              width=w, height=logo_height,
                              preserveAspectRatio=True, mask="auto")
        except Exception:
            pass

    canvas.setFont("DejaVu", 8)
    canvas.setFillColor(PRIMARY)
    tw = stringWidth(CONTACT_TEXT, "DejaVu", 8)
    canvas.drawString((page_w - tw) / 2,
                       page_h - top_pad - logo_height / 2 - 3,
                       CONTACT_TEXT)

    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.5)
    canvas.line(side_pad,
                page_h - top_pad - logo_height - 4 * mm,
                page_w - side_pad,
                page_h - top_pad - logo_height - 4 * mm)

    canvas.setFont("DejaVu", 8)
    canvas.setFillColor(GREY)
    page_num = f"Страница {doc.page}"
    tw = stringWidth(page_num, "DejaVu", 8)
    canvas.drawString((page_w - tw) / 2, 8 * mm, page_num)

    canvas.restoreState()


# =============== ОЧИСТКА ТЕКСТА ===============

_MOJIBAKE_RE = re.compile(
    r"[ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖ×ØÙÚÛÜÝÞßàáâãäåæçèéêëìíîïðñòóôõö÷øùúûüýþÿ]")


def _fix_mojibake(s: str) -> str:
    if not isinstance(s, str):
        return s
    if not _MOJIBAKE_RE.search(s):
        return s
    for enc_from in ("latin-1", "cp1252"):
        for enc_to in ("cp1251", "utf-8"):
            try:
                fixed = s.encode(enc_from).decode(enc_to)
                if not _MOJIBAKE_RE.search(fixed):
                    return fixed
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
    return s


def _clean_text(s: str) -> str:
    if not isinstance(s, str):
        s = str(s)
    s = re.sub(r"[\u200b-\u200f\u202a-\u202e\u2060-\u206f\ufeff]", "", s)
    s = "".join(ch for ch in s if ch.isprintable() or ch in "\n\t")
    s = re.sub(r"^[\u00a1-\u00ff\s]+", "", s)
    s = re.sub(r"[\u00a1-\u00bf]+", " ", s)
    return s


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
        ("Крахмал", "Крахмал", True),
        ("Сахар", "Сахар", True),
        ("Перев. ОВ", "Перев. ОВ, %", True),
        ("Низкий НДК", "НДК", False),
    ]
    labels = [p[0] for p in params]
    data = []
    for _, col, higher in params:
        vals = pd.to_numeric(df[col], errors="coerce").fillna(0)
        if vals.max() == vals.min():
            score = pd.Series([50] * len(vals))
        elif higher:
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
    s = _fix_mojibake(s)
    s = _clean_text(s)
    s = s.replace("&", "&amp;")
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"<i>\1</i>", s)
    return s


def _md_to_story(text: str, styles):
    story = []
    text = _fix_mojibake(text)
    lines = text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i].rstrip()

        if (line.startswith("|") and line.endswith("|")
                and i + 1 < len(lines)
                and re.match(r"^\|[\s\-:|]+\|$", lines[i + 1].strip())):
            table_lines = []
            j = i
            while j < len(lines) and lines[j].strip().startswith("|"):
                table_lines.append(lines[j].strip())
                j += 1

            header_cells = [c.strip()
                            for c in table_lines[0].strip("|").split("|")]
            data_rows = []
            for tl in table_lines[2:]:
                cells = [c.strip() for c in tl.strip("|").split("|")]
                data_rows.append(cells)

            table_data = [[_inline_md(c) for c in header_cells]]
            for row in data_rows:
                row = (row + [""] * len(header_cells))[:len(header_cells)]
                table_data.append([_inline_md(c) for c in row])

            n_cols = len(header_cells)
            avail = 180 * mm
            if n_cols >= 8:
                weights = [0.08, 0.10, 0.09, 0.12, 0.10, 0.09, 0.12, 0.30]
            elif n_cols == 7:
                weights = [0.10, 0.10, 0.12, 0.12, 0.10, 0.13, 0.33]
            else:
                weights = [1.0 / n_cols] * n_cols
            col_widths = [avail * w for w in weights[:n_cols]]

            t = Table(table_data, colWidths=col_widths, repeatRows=1)
            t.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "DejaVu-Bold"),
                ("FONTNAME", (0, 1), (-1, -1), "DejaVu"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.3, GREY),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.white, LIGHT]),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ]))
            story.append(Spacer(1, 4))
            story.append(t)
            story.append(Spacer(1, 6))

            i = j
            continue

        if not line:
            story.append(Spacer(1, 3))
            i += 1
            continue
        if line.startswith("### "):
            story.append(Paragraph(_inline_md(line[4:]), styles["pdf_h3"]))
        elif line.startswith("## "):
            story.append(Paragraph(_inline_md(line[3:]), styles["pdf_h2"]))
        elif line.startswith("# "):
            story.append(Paragraph(_inline_md(line[2:]), styles["pdf_h1"]))
        elif line.startswith("  - ") or line.startswith("  • "):
            story.append(Paragraph(
                f"&nbsp;&nbsp;&nbsp;◦ {_inline_md(line[4:].lstrip('-• '))}",
                styles["pdf_bullet2"]))
        elif line.startswith("- ") or line.startswith("* "):
            story.append(Paragraph(f"• {_inline_md(line[2:])}",
                                    styles["pdf_bullet"]))
        else:
            m = re.match(r"^(\d+)\.\s+(.*)$", line)
            if m:
                story.append(Paragraph(
                    f"{m.group(1)}. {_inline_md(m.group(2))}",
                    styles["pdf_bullet"]))
            else:
                story.append(Paragraph(_inline_md(line), styles["pdf_body"]))
        i += 1
    return story


# =============== КОРРЕКТИРОВКИ ===============

def _fmt_correction(c) -> str:
    if not isinstance(c, dict):
        return str(c)
    feed = c.get("корм", "—")
    if "кг" in c:
        nel = f" (+{c['NEL']} МДж NEL)" if "NEL" in c else ""
        return f"{feed}: {c['кг']} кг/сутки{nel}"
    if "кг СВ" in c:
        nxp = f" (+{c['nXP']} г nXP)" if "nXP" in c else ""
        return f"{feed}: {c['кг СВ']} кг СВ/сутки{nxp}"
    return str(c)


# =============== СТИЛИ И ТАБЛИЦЫ ===============

def _make_styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("pdf_title", parent=styles["Title"],
                              fontName="DejaVu-Bold", fontSize=20,
                              textColor=PRIMARY, spaceAfter=8))
    styles.add(ParagraphStyle("pdf_h1", parent=styles["Heading1"],
                              fontName="DejaVu-Bold", fontSize=15,
                              textColor=PRIMARY, spaceAfter=6, spaceBefore=10))
    styles.add(ParagraphStyle("pdf_h2", parent=styles["Heading2"],
                              fontName="DejaVu-Bold", fontSize=12,
                              textColor=colors.HexColor("#1F4E2C"),
                              spaceAfter=4, spaceBefore=8))
    styles.add(ParagraphStyle("pdf_h3", parent=styles["Heading3"],
                              fontName="DejaVu-Bold", fontSize=11,
                              textColor=colors.HexColor("#2C7A3E"),
                              spaceAfter=2, spaceBefore=6))
    styles.add(ParagraphStyle("pdf_body", parent=styles["BodyText"],
                              fontName="DejaVu", fontSize=10, leading=14))
    styles.add(ParagraphStyle("pdf_bullet", parent=styles["BodyText"],
                              fontName="DejaVu", fontSize=10, leading=14,
                              leftIndent=12))
    styles.add(ParagraphStyle("pdf_bullet2", parent=styles["BodyText"],
                              fontName="DejaVu", fontSize=9, leading=13,
                              leftIndent=24))
    styles.add(ParagraphStyle("pdf_small", parent=styles["BodyText"],
                              fontName="DejaVu", fontSize=8,
                              textColor=GREY, leading=11))
    styles.add(ParagraphStyle("pdf_table_row", parent=styles["BodyText"],
                              fontName="DejaVu", fontSize=9, leading=12))
    return styles


def _make_table(data, col_widths, header_color=PRIMARY):
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), header_color),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "DejaVu-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "DejaVu"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.3, GREY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return t


# =============== PDF ДЛЯ АНАЛИЗА КОРМОВ ===============

def generate_pdf(analysis: dict, rations: dict, ai_text: str,
                 live_weight: float, milk_yield: float) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=25 * mm, bottomMargin=18 * mm,
        title="Отчёт по анализу кормов", author="Feed Analyzer",
    )

    styles = _make_styles()
    story = []
    date_str = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")

    story.append(Paragraph("Отчёт по анализу кормов", styles["pdf_title"]))
    story.append(Paragraph(f"Сформирован: {date_str}", styles["pdf_small"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"<b>Параметры коровы:</b> живая масса {live_weight} кг, "
        f"суточный удой {milk_yield} кг", styles["pdf_body"]))
    story.append(Paragraph(
        f"<b>Проанализировано образцов:</b> {len(analysis['ratings'])}",
        styles["pdf_body"]))
    story.append(Spacer(1, 10))

    story.append(Paragraph("1. Сводная таблица образцов", styles["pdf_h1"]))
    summary_data = [["№", "Образец", "Балл", "NEL-VC",
                     "Крахмал", "НДК", "RNB"]]
    for i, s in enumerate(analysis["ratings"], 1):
        summary_data.append([
            str(i), str(s["name"])[:22],
            f"{s['score']:.1f}" if s["score"] is not None else "—",
            f"{s['NEL_VC']:.2f}" if s["NEL_VC"] is not None else "—",
            f"{s['starch']:.0f}" if s["starch"] is not None else "—",
            f"{s['NDF']:.0f}" if s["NDF"] is not None else "—",
            f"{s['RNB']:.1f}" if s["RNB"] is not None else "—",
        ])
    story.append(_make_table(summary_data,
                              [12*mm, 46*mm, 18*mm, 22*mm,
                               22*mm, 18*mm, 20*mm]))
    story.append(PageBreak())

    story.append(Paragraph("2. Графики сравнения", styles["pdf_h1"]))

    df = pd.DataFrame([{
        "Образец": s["name"],
        "Балл": s["score"] or 0,
        "NEL-VC": s["NEL_VC"] or 0,
        "Крахмал": s["starch"] or 0,
        "Сахар": s["sugar"] or 0,
        "НДК": s["NDF"] or 0,
        "Перев. ОВ, %": s["dOM"] or 0,
        "RNB": s["RNB"] or 0,
    } for s in analysis["ratings"]])

    story.append(Paragraph("2.1 Рейтинг образцов", styles["pdf_h2"]))
    story.append(Image(_bar_chart(df["Образец"].tolist(),
                                    df["Балл"].tolist(),
                                    "Рейтинг по баллу качества"),
                        width=170*mm, height=75*mm))

    story.append(Paragraph("2.2 Энергия: NEL-VC", styles["pdf_h2"]))
    df_nel = df.sort_values("NEL-VC", ascending=False)
    story.append(Image(_bar_chart(df_nel["Образец"].tolist(),
                                    df_nel["NEL-VC"].tolist(),
                                    "NEL-VC (МДж/кг СВ)", color="#3498DB"),
                        width=170*mm, height=75*mm))

    story.append(Paragraph("2.3 Крахмал", styles["pdf_h2"]))
    df_st = df.sort_values("Крахмал", ascending=False)
    story.append(Image(_bar_chart(df_st["Образец"].tolist(),
                                    df_st["Крахмал"].tolist(),
                                    "Крахмал (г/кг СВ)", color="#F39C12"),
                        width=170*mm, height=75*mm))
    story.append(PageBreak())

    story.append(Paragraph("2.4 Углеводный баланс", styles["pdf_h2"]))
    story.append(Image(_grouped_chart(
        df["Образец"].tolist(),
        {"Крахмал": df["Крахмал"].tolist(),
         "Сахар": df["Сахар"].tolist(),
         "НДК": df["НДК"].tolist()},
        "Крахмал, сахар, НДК"), width=170*mm, height=85*mm))

    story.append(Paragraph("2.5 Профиль образцов (радар)", styles["pdf_h2"]))
    try:
        story.append(Image(_radar_chart(df, top_n=4),
                            width=145*mm, height=120*mm))
    except Exception as e:
        story.append(Paragraph(f"Радар не построен: {e}",
                                styles["pdf_small"]))
    story.append(PageBreak())

    story.append(Paragraph("3. Расчёт рационов для всех образцов",
                            styles["pdf_h1"]))
    for i, (name, r) in enumerate(rations.items(), 1):
        story.append(Paragraph(f"3.{i}. {name}", styles["pdf_h2"]))
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
        story.append(_make_table(metrics,
                                  [42*mm, 28*mm, 28*mm, 42*mm],
                                  header_color=ACCENT))
        story.append(Spacer(1, 5))
        comp = [["Корм", "СВ, кг", "Нат. вес, кг",
                 "NEL, МДж", "nXP, г", "НДК, г"]]
        for feed, vals in r["ration"].items():
            comp.append([feed, f"{vals['dm']:.2f}", f"{vals['nat']:.2f}",
                         f"{vals['NEL']:.1f}", f"{vals['nXP']:.0f}",
                         f"{vals['NDF']:.0f}"])
        story.append(_make_table(comp,
                                  [52*mm, 20*mm, 28*mm,
                                   24*mm, 20*mm, 22*mm]))
        if r["corrections"]:
            story.append(Spacer(1, 4))
            story.append(Paragraph("<b>Корректировки:</b>", styles["pdf_body"]))
            for c in r["corrections"]:
                story.append(Paragraph(f"• {_fmt_correction(c)}",
                                        styles["pdf_bullet"]))
        story.append(Spacer(1, 12))

    story.append(PageBreak())
    story.append(Paragraph("4. Выводы зоотехника (ИИ)", styles["pdf_h1"]))
    story.append(Spacer(1, 4))
    story.extend(_md_to_story(ai_text, styles))
    story.append(Spacer(1, 20))
    story.append(Paragraph(
        f"Отчёт сформирован автоматически • {date_str} • Feed Analyzer",
        styles["pdf_small"]))

    doc.build(story, onFirstPage=_draw_page_decorations,
              onLaterPages=_draw_page_decorations)
    buffer.seek(0)
    return buffer.getvalue()


# =============== PDF ДЛЯ ЭКОНОМИКИ ===============

def generate_economics_pdf(result: dict,
                            silenta_name: str,
                            competitor_name: str,
                            silo_demand_t: float,
                            grain_price: float,
                            ai_text: str = "",
                            silenta_extra: dict = None,
                            competitor_extra: dict = None,
                            feed_econ: dict = None,
                            feed_params: dict = None,
                            surplus: dict = None,
                            total_grand: float = 0.0) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=25 * mm, bottomMargin=18 * mm,
        title="Экономика выращивания силосной кукурузы",
        author="Feed Analyzer",
    )

    styles = _make_styles()
    story = []
    date_str = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")

    s = result["silenta"]
    c = result["competitor"]

    story.append(Paragraph("Экономика выращивания силосной кукурузы",
                            styles["pdf_title"]))
    story.append(Paragraph(f"Сформирован: {date_str}", styles["pdf_small"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        f"<b>Потребность в силосе:</b> "
        f"{silo_demand_t:,.1f} т/год".replace(",", " "),
        styles["pdf_body"]))
    story.append(Paragraph(
        f"<b>Цена кукурузного зерна:</b> "
        f"{grain_price:,.0f} за 1 т".replace(",", " "),
        styles["pdf_body"]))
    story.append(Spacer(1, 10))

    story.append(Paragraph("1. Общие параметры", styles["pdf_h1"]))
    common = [
        ["Показатель", silenta_name, competitor_name],
        ["Урожайность ЗМ, ц/га",
         f"{s['yield_green']:.1f}", f"{c['yield_green']:.1f}"],
        ["Содержание СВ, %", f"{s['dm_pct']:.1f}", f"{c['dm_pct']:.1f}"],
        ["ОЭ, МДж/кг СВ", f"{s['me']:.2f}", f"{c['me']:.2f}"],
    ]
    story.append(_make_table(common, [70*mm, 55*mm, 55*mm]))
    story.append(Spacer(1, 10))

    story.append(Paragraph("2. Сравнение гибридов", styles["pdf_h1"]))
    comparison = [
        ["Показатель", silenta_name, competitor_name],
        ["Площадь сева, га", f"{s['area']:.1f}", f"{c['area']:.1f}"],
        ["Затраты на семена, на 1 га",
         f"{s['seed_cost_per_ha']:,.0f}".replace(",", " "),
         f"{c['seed_cost_per_ha']:,.0f}".replace(",", " ")],
        ["Затраты на всю площадь",
         f"{s['total_cost']:,.0f}".replace(",", " "),
         f"{c['total_cost']:,.0f}".replace(",", " ")],
        ["Урожайность СВ, ц/га",
         f"{s['dm_yield']:.1f}", f"{c['dm_yield']:.1f}"],
        ["Валовый сбор СВ, ц",
         f"{s['dm_total']:,.0f}".replace(",", " "),
         f"{c['dm_total']:,.0f}".replace(",", " ")],
        ["Выход ОЭ, МДж/га",
         f"{s['me_per_ha']:,.0f}".replace(",", " "),
         f"{c['me_per_ha']:,.0f}".replace(",", " ")],
    ]
    story.append(_make_table(comparison, [70*mm, 55*mm, 55*mm]))
    story.append(Spacer(1, 10))

    next_section = 3

    if silenta_extra or competitor_extra:
        story.append(Paragraph(f"{next_section}. Лабораторные данные",
                                styles["pdf_h1"]))

        def _v(extra, key):
            if not extra:
                return "—"
            val = extra.get(key)
            return "—" if val is None else str(val)

        lab_data = [
            ["Показатель", silenta_name, competitor_name],
            ["Крахмал, г/кг СВ",
             _v(silenta_extra, "starch"), _v(competitor_extra, "starch")],
            ["НДК, г/кг СВ",
             _v(silenta_extra, "NDF"), _v(competitor_extra, "NDF")],
            ["Перев. ОВ, %",
             _v(silenta_extra, "dOM"), _v(competitor_extra, "dOM")],
            ["RNB, г/кг СВ",
             _v(silenta_extra, "RNB"), _v(competitor_extra, "RNB")],
        ]
        story.append(_make_table(lab_data, [70*mm, 55*mm, 55*mm],
                                  header_color=ACCENT))
        story.append(Spacer(1, 10))
        next_section += 1

    story.append(Paragraph(f"{next_section}. Экономия на выращивании",
                            styles["pdf_h1"]))
    econ_data = [
        ["Показатель", "Значение"],
        ["Освобождено площади", f"{result['freed_area']:.1f} га"],
        ["Экономия затрат",
         f"{result['saving_field']:,.0f}".replace(",", " ")],
        ["Разница выхода ОЭ",
         f"{result['delta_me_per_ha']:,.0f} МДж/га".replace(",", " ")],
        ["Эквивалент кукурузного зерна",
         f"{result['grain_equiv_per_ha']:,.0f} кг/га".replace(",", " ")],
        ["Экономия на зерне",
         f"{result['saving_grain']:,.0f}".replace(",", " ")],
        ["ИТОГО по выращиванию",
         f"{result['total_saving']:,.0f}".replace(",", " ")],
    ]
    story.append(_make_table(econ_data, [95*mm, 85*mm], header_color=ACCENT))
    story.append(Spacer(1, 10))
    next_section += 1

    if surplus:
        story.append(Paragraph(f"{next_section}. Излишек силоса "
                                f"(при одинаковой площади)",
                                styles["pdf_h1"]))
        story.append(Paragraph(
            f"Если оба гибрида засеять на одинаковую площадь "
            f"({surplus['same_area']:.1f} га), то {silenta_name} даст "
            f"больше силоса. Этот излишек можно продать.",
            styles["pdf_body"]))
        story.append(Spacer(1, 6))

        sur_data = [
            ["Показатель", "Значение"],
            ["Излишек СВ", f"{surplus['surplus_dm_t']:,.1f} т СВ"
                              .replace(",", " ")],
            ["Излишек ЗМ", f"{surplus['surplus_gm_t']:,.1f} т ЗМ"
                              .replace(",", " ")],
            ["Эквивалент зерна по ОЭ",
             f"{surplus['surplus_grain_t']:,.1f} т зерна"
             .replace(",", " ")],
            ["Оценка: продажа силоса",
             f"{surplus['saving_sale']:,.0f}".replace(",", " ")],
            ["Оценка: замена зерна",
             f"{surplus['saving_grain_equiv']:,.0f}".replace(",", " ")],
        ]
        story.append(_make_table(sur_data, [95*mm, 85*mm],
                                  header_color=ACCENT))
        story.append(Spacer(1, 10))
        next_section += 1

    if feed_econ and feed_params:
        story.append(Paragraph(
            f"{next_section}. Экономия на кормах "
            f"({feed_params.get('n_cows', 0)} голов)",
            styles["pdf_h1"]))

        story.append(Paragraph(
            "Расход на 1 корову в день (кг нат. веса)",
            styles["pdf_h2"]))
        feed_table = [
            ["Корм", silenta_name, competitor_name, "Разница"],
            ["Силос",
             f"{feed_econ['silo1_nat']:.2f}",
             f"{feed_econ['silo2_nat']:.2f}",
             f"{feed_econ['delta_silo_nat']:+.2f}"],
            ["Комбикорм",
             f"{feed_econ['conc1_nat']:.2f}",
             f"{feed_econ['conc2_nat']:.2f}",
             f"{feed_econ['delta_conc_nat']:+.2f}"],
            ["Сено",
             f"{feed_econ['hay1_nat']:.2f}",
             f"{feed_econ['hay2_nat']:.2f}",
             f"{feed_econ['delta_hay_nat']:+.2f}"],
            ["Сенаж",
             f"{feed_econ['haylage1_nat']:.2f}",
             f"{feed_econ['haylage2_nat']:.2f}",
             f"{feed_econ['delta_haylage_nat']:+.2f}"],
        ]
        story.append(_make_table(feed_table, [40*mm, 40*mm, 40*mm, 40*mm]))
        story.append(Paragraph(
            "Отрицательная разница по силосу перекрывается экономией "
            "на комбикорме.",
            styles["pdf_small"]))
        story.append(Spacer(1, 8))

        story.append(Paragraph(
            f"Экономия на поголовье ({feed_econ.get('n_cows', 0)} голов)",
            styles["pdf_h2"]))
        saving_table = [
            ["Источник", "В день", "В год"],
            ["Силос",
             f"{feed_econ['saving_silo_day']:,.0f}".replace(",", " "),
             f"{feed_econ['saving_silo_year']:,.0f}".replace(",", " ")],
            ["Комбикорм",
             f"{feed_econ['saving_conc_day']:,.0f}".replace(",", " "),
             f"{feed_econ['saving_conc_year']:,.0f}".replace(",", " ")],
            ["Сено",
             f"{feed_econ['saving_hay_day']:,.0f}".replace(",", " "),
             f"{feed_econ['saving_hay_year']:,.0f}".replace(",", " ")],
            ["Сенаж",
             f"{feed_econ['saving_haylage_day']:,.0f}".replace(",", " "),
             f"{feed_econ['saving_haylage_year']:,.0f}".replace(",", " ")],
            ["ИТОГО",
             f"{feed_econ['total_feed_day']:,.0f}".replace(",", " "),
             f"{feed_econ['total_feed_year']:,.0f}".replace(",", " ")],
        ]
        story.append(_make_table(saving_table, [60*mm, 55*mm, 60*mm],
                                  header_color=ACCENT))
        story.append(Spacer(1, 10))
        next_section += 1

    story.append(Paragraph(f"{next_section}. Совокупная годовая экономия",
                            styles["pdf_h1"]))
    grand_rows = [
        ["Источник", "В год"],
        ["Выращивание",
         f"{result['total_saving']:,.0f}".replace(",", " ")],
    ]
    if feed_econ:
        grand_rows.append(["Кормление",
                            f"{feed_econ['total_feed_year']:,.0f}"
                            .replace(",", " ")])
    if surplus:
        grand_rows.append(["Излишек силоса",
                            f"{surplus['saving_sale']:,.0f}"
                            .replace(",", " ")])
    grand_rows.append(["ИТОГО за год",
                        f"{total_grand:,.0f}".replace(",", " ")])
    story.append(_make_table(grand_rows, [95*mm, 85*mm],
                              header_color=PRIMARY))
    story.append(Spacer(1, 10))
    next_section += 1

    story.append(PageBreak())

    story.append(Paragraph(f"{next_section}. Графики", styles["pdf_h1"]))

    story.append(Paragraph("Выход ОЭ с гектара", styles["pdf_h2"]))
    story.append(Image(_bar_chart(
        [silenta_name, competitor_name],
        [s["me_per_ha"], c["me_per_ha"]],
        "Выход ОЭ (МДж/га)"), width=140*mm, height=60*mm))

    story.append(Paragraph("Затраты на всю площадь", styles["pdf_h2"]))
    story.append(Image(_bar_chart(
        [silenta_name, competitor_name],
        [s["total_cost"], c["total_cost"]],
        "Затраты на всю площадь", color="#3498DB"),
        width=140*mm, height=60*mm))

    if feed_econ:
        story.append(Paragraph("Экономия на кормах в год",
                                styles["pdf_h2"]))
        story.append(Image(_bar_chart(
            ["Силос", "Комбикорм", "Сено", "Сенаж"],
            [feed_econ["saving_silo_year"],
             feed_econ["saving_conc_year"],
             feed_econ["saving_hay_year"],
             feed_econ["saving_haylage_year"]],
            "Экономия на кормах в год", color="#F39C12"),
            width=140*mm, height=60*mm))

    story.append(PageBreak())

    story.append(Paragraph(f"{next_section + 1}. Экономический вывод",
                            styles["pdf_h1"]))
    story.append(Spacer(1, 4))
    if ai_text:
        story.extend(_md_to_story(ai_text, styles))
    else:
        story.append(Paragraph("Вывод не сформирован.",
                                styles["pdf_body"]))

    story.append(Spacer(1, 20))
    story.append(Paragraph(
        f"Отчёт сформирован автоматически • {date_str} • Feed Analyzer",
        styles["pdf_small"]))

    doc.build(story, onFirstPage=_draw_page_decorations,
              onLaterPages=_draw_page_decorations)
    buffer.seek(0)
    return buffer.getvalue()
