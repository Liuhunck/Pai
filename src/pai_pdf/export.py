"""Both exports are generated from the same document representation."""

import html
import json
from pathlib import Path

from .chunking import chunk_document


def _text(text):
    # Preserve literal source punctuation, HTML and Markdown markers.
    text = html.escape(text, quote=False)
    for char in ("\\", "`", "*", "_", "[", "]", "#"):
        text = text.replace(char, "\\" + char)
    return text


def markdown(document):
    parts = []
    for page in document["pages"]:
        parts.append(f"<!-- page:{page['number']} status:{page['status']} -->")
        if page["status"] != "success":
            parts.append(f"> 第 {page['number']} 页未完整解析，详见 report.json。")
        for block in page["blocks"]:
            parts.append(f"<!-- block:{block['id']} -->")
            if block["type"] == "table":
                rows = block["rows"]
                if "merged_or_missing_table_cells" in block["quality"]["flags"]:
                    parts.append(
                        "> 此表格可能包含合并或缺失单元格；以下仅为提取到的网格，需对照原文。"
                    )
                # HTML keeps every row as data; do not invent a table header.
                table = ["<table>"]
                for row in rows:
                    table.append(
                        "<tr>"
                        + "".join(
                            "<td>" + html.escape(cell or "").replace("\n", "<br>") + "</td>"
                            for cell in row
                        )
                        + "</tr>"
                    )
                table.append("</table>")
                parts.append("\n".join(table))
            elif block["type"] == "heading":
                parts.append("#" * block["heading_level"] + " " + _text(block["text"]))
            else:
                parts.append(_text(block["text"]))
        for img in page["images"]:
            if img.get("asset"):
                parts.append(
                    f"<!-- image:{img['id']} -->\n![第 {page['number']} 页图片]({img['asset']})"
                )
    return "\n\n".join(parts) + "\n"


def write_outputs(document, destination, peak_rss_mib=None):
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    report = {k: v for k, v in document.items() if k not in {"pages", "metadata", "coordinates"}}
    report["process_peak_rss_mib"] = peak_rss_mib
    report["pages_needing_review"] = [
        p["number"] for p in document["pages"] if p["quality"]["needs_review"]
    ]
    report["page_results"] = [
        {
            "number": p["number"],
            "status": p["status"],
            "quality": p["quality"],
            "processing": p["processing"],
        }
        for p in document["pages"]
    ]
    for name, value in (("document.json", document), ("report.json", report)):
        (destination / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
        )
    (destination / "document.md").write_text(markdown(document), encoding="utf-8")
    chunks = chunk_document(document)
    (destination / "chunks.jsonl").write_text(
        "".join(json.dumps(c, ensure_ascii=False, allow_nan=False) + "\n" for c in chunks),
        encoding="utf-8",
    )
