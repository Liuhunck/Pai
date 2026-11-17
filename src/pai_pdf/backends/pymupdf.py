"""PyMuPDF-specific extraction and rendering; no model dependencies."""

import math

from ..layout import area, bad_text_ratio, deduplicate, intersection, rounded, union


def native_lines(page, fitz):
    flags = fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES
    content = page.get_text("dict", flags=flags)
    lines = []
    for group, block in enumerate(content["blocks"]):
        if block["type"] != 0:
            continue
        for line in block["lines"]:
            text = "".join(s["text"] for s in line["spans"]).strip()
            box = intersection(line["bbox"], list(page.rect))
            if not text or area(box) <= 0:
                continue
            issues = ["suspicious_characters"] if bad_text_ratio(text) > 0.03 else []
            direction = line.get("dir", (1, 0))
            if abs(direction[0] - 1) > 0.05 or abs(direction[1]) > 0.05:
                issues.append("rotated_text")
            size = max((s["size"] for s in line["spans"] if s["text"].strip()), default=0)
            lines.append(
                {
                    "text": text,
                    "bbox": rounded(box),
                    "source": "native",
                    "confidence": None,
                    "font_size": round(size, 2),
                    "group": group,
                    "flags": issues,
                    "bold": all(s.get("flags", 0) & 16 for s in line["spans"] if s["text"].strip()),
                }
            )
    lines, _, removed = deduplicate(lines)
    return lines, removed


def image_regions(page):
    regions = []
    for info in page.get_image_info():
        box = intersection(list(info["bbox"]), list(page.rect))
        if area(box) <= 0:
            continue
        if not all(math.isfinite(v) for v in box):
            continue
        regions.append(box)
    # Overlapping tiles and duplicate image objects must not be OCR'd repeatedly.
    merged = []
    for box in sorted(regions, key=area, reverse=True):
        for other in merged:
            overlap = area(intersection(box, other)) / max(1, min(area(box), area(other)))
            if overlap >= 0.8:
                other[:] = union([box, other])
                break
        else:
            merged.append(box)
    return sorted(merged, key=lambda b: (b[1], b[0]))


def extract_tables(page, native):
    tables, warnings = [], []
    try:
        finder = page.find_tables(strategy="lines_strict")
        for table in finder.tables:
            rows = table.extract()
            if len(rows) < 2 or max(map(len, rows), default=0) < 2:
                continue
            if not any(cell for row in rows for cell in row):
                continue
            # Only absorb lines that are substantially inside this table.
            contained = [
                item_line
                for item_line in native
                if area(intersection(item_line["bbox"], table.bbox))
                / max(1, area(item_line["bbox"]))
                > 0.8
            ]
            cells = []
            for r, row in enumerate(table.rows):
                for c, box in enumerate(row.cells):
                    cells.append(
                        {
                            "row": r,
                            "column": c,
                            "bbox": rounded(box) if box is not None else None,
                            "text": rows[r][c] if r < len(rows) and c < len(rows[r]) else None,
                        }
                    )
            flags = (
                ["merged_or_missing_table_cells"] if any(c["bbox"] is None for c in cells) else []
            )
            tables.append(
                {
                    "type": "table",
                    "source": "native",
                    "bbox": rounded(table.bbox),
                    "text": "\n".join(" | ".join(c or "" for c in row) for row in rows),
                    "rows": rows,
                    "cells": cells,
                    "lines": contained,
                    "flags": flags,
                    "header_inferred": False,
                }
            )
    except Exception as exc:
        warnings.append({"code": "table_extraction_failed", "detail": str(exc)})
    return tables, warnings


def render(page, box, options, fitz):
    scale = min(options.dpi / 72, math.sqrt(options.max_pixels / max(1, area(box))))
    pix = page.get_pixmap(
        matrix=fitz.Matrix(scale, scale),
        clip=fitz.Rect(box),
        colorspace=fitz.csRGB,
        alpha=False,
        annots=False,
    )
    return pix.tobytes("png"), (pix.x, pix.y), scale
