def _md_to_story(text: str, styles):
    """Парсит markdown, включая таблицы, в flowable-элементы reportlab."""
    story = []
    text = _fix_mojibake(text)
    lines = text.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i].rstrip()

        # --- Определяем начало markdown-таблицы ---
        if (line.startswith("|") and line.endswith("|") and i + 1 < len(lines)
                and re.match(r"^\|[\s\-:|]+\|$", lines[i + 1].strip())):
            # Собираем все строки таблицы
            table_lines = []
            j = i
            while j < len(lines) and lines[j].strip().startswith("|"):
                table_lines.append(lines[j].strip())
                j += 1

            # Первая строка — заголовки, вторая — разделитель, остальное — данные
            header_cells = [c.strip() for c in table_lines[0].strip("|").split("|")]
            data_rows = []
            for tl in table_lines[2:]:
                cells = [c.strip() for c in tl.strip("|").split("|")]
                data_rows.append(cells)

            # Строим reportlab-таблицу
            table_data = [[_inline_md(c) for c in header_cells]]
            for row in data_rows:
                # выравниваем длину
                row = (row + [""] * len(header_cells))[:len(header_cells)]
                table_data.append([_inline_md(c) for c in row])

            n_cols = len(header_cells)
            # Ширины колонок — пропорционально содержимому
            avail = 180 * mm
            if n_cols >= 8:
                weights = [0.10, 0.16, 0.09, 0.11, 0.10, 0.09, 0.11, 0.24]
            elif n_cols == 7:
                weights = [0.12, 0.10, 0.12, 0.11, 0.10, 0.12, 0.33]
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

        # --- Обычные строки ---
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
