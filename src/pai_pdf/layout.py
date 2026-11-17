"""Geometry and conservative structure heuristics; standard library only."""

import math
import re
import unicodedata
from collections import Counter
from difflib import SequenceMatcher
from statistics import median

from .paper import CAPTION, heading_level


def area(box):
    return max(0, box[2] - box[0]) * max(0, box[3] - box[1])


def intersection(a, b):
    return [max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])]


def union(boxes):
    return [
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    ]


def rounded(box):
    return [round(float(v), 3) for v in box]


def bad_text_ratio(text):
    if not text:
        return 0.0
    bad = sum(
        c == "\ufffd" or (unicodedata.category(c) in {"Cc", "Cs", "Co"} and c not in "\t\n\r")
        for c in text
    )
    return bad / len(text)


def normalized(text):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text)).casefold()


def deduplicate(lines, references=()):
    """Keep repeated text at different positions. Prefer native text in same region."""
    kept, conflicts, removed = [], 0, 0
    for line in lines:
        duplicate = False
        for other in [*references, *kept]:
            overlap = area(intersection(line["bbox"], other["bbox"]))
            if overlap / max(1, min(area(line["bbox"]), area(other["bbox"]))) < 0.65:
                continue
            a, b = normalized(line["text"]), normalized(other["text"])
            if a == b or (min(len(a), len(b)) >= 8 and SequenceMatcher(None, a, b).ratio() >= 0.88):
                duplicate = True
                removed += 1
                break
            if line["source"] != other["source"] and a and b:
                if "source_text_conflict" not in line["flags"]:
                    line["flags"].append("source_text_conflict")
                    conflicts += 1
        if not duplicate:
            kept.append(line)
    return kept, conflicts, removed


def _gaps(items, axis):
    intervals = sorted((i["bbox"][axis], i["bbox"][axis + 2]) for i in items)
    end = intervals[0][1]
    gaps = []
    for start, stop in intervals[1:]:
        if start > end:
            gaps.append((end, start))
        end = max(end, stop)
    return gaps


def reading_order(items, depth=0):
    """Whitespace cuts for simple columns, then geometric top-to-bottom order."""
    if len(items) < 2 or depth >= 24:
        return sorted(items, key=lambda i: (i["bbox"][1], i["bbox"][0])), False
    box = union([i["bbox"] for i in items])
    # Prefer an actual gutter, with content on both sides at overlapping heights.
    for lo, hi in sorted(_gaps(items, 0), key=lambda g: g[1] - g[0], reverse=True):
        if hi - lo < max(18, (box[2] - box[0]) * 0.035):
            continue
        left = [i for i in items if i["bbox"][2] <= lo + 0.01]
        right = [i for i in items if i["bbox"][0] >= hi - 0.01]
        if len(left) < 2 or len(right) < 2:
            continue
        a, b = union([i["bbox"] for i in left]), union([i["bbox"] for i in right])
        overlap = min(a[3], b[3]) - max(a[1], b[1])
        if overlap < 0.3 * min(a[3] - a[1], b[3] - b[1]):
            continue
        item_line, _ = reading_order(left, depth + 1)
        r, _ = reading_order(right, depth + 1)
        return item_line + r, True
    # A full-width heading often blocks a column split: first separate its band.
    gaps = _gaps(items, 1)
    if gaps:
        lo, hi = max(gaps, key=lambda g: g[1] - g[0])
        typical_height = median(i["bbox"][3] - i["bbox"][1] for i in items)
        if hi - lo > max(5, typical_height * 0.6):
            above = [i for i in items if i["bbox"][3] <= lo + 0.01]
            below = [i for i in items if i["bbox"][1] >= hi - 0.01]
            a, ac = reading_order(above, depth + 1)
            b, bc = reading_order(below, depth + 1)
            return a + b, ac or bc
    return sorted(items, key=lambda i: (i["bbox"][1], i["bbox"][0])), False


def join_lines(texts):
    result = ""
    for text in texts:
        text = text.strip()
        if not text:
            continue
        if result:

            def cjk(c):
                return (
                    "\u3400" <= c <= "\u9fff"
                    or "\u3000" <= c <= "\u303f"
                    or "\uff00" <= c <= "\uffef"
                )

            result += "" if cjk(result[-1]) and cjk(text[0]) else " "
        result += text
    return result


LIST = re.compile(r"^(?:[•●▪◦‣·]\s*|[-*]\s+|\d+[.)、]\s*|[（(]\d+[)）]\s*)")


def make_blocks(lines, tables, page_number):
    sizes = Counter()
    for line in lines:
        if line.get("font_size"):
            sizes[round(line["font_size"], 1)] += max(1, len(line["text"]))
    body_size = sizes.most_common(1)[0][0] if sizes else 0
    units = [{"bbox": item_line["bbox"], "line": item_line} for item_line in lines]
    units += [{"bbox": t["bbox"], "table": t} for t in tables]
    ordered, columns = reading_order(units)
    blocks = []
    for unit in ordered:
        if "table" in unit:
            blocks.append(unit["table"])
            continue
        line = unit["line"]
        kind, level = "paragraph", None
        prominent = line.get("bold", False) or bool(
            body_size and (line.get("font_size") or 0) >= body_size * 1.15
        )
        section_level = heading_level(line["text"], prominent=prominent)
        if section_level:
            kind, level = "heading", section_level
        elif CAPTION.match(line["text"]):
            kind = "caption"
        elif LIST.match(line["text"]):
            kind = "list_item"
        elif (
            body_size
            and (line.get("font_size") or 0) >= body_size * 1.25
            and len(line["text"]) <= 120
            and any(c.isalpha() for c in line["text"])
        ):
            kind = "heading"
            level = 1 if line["font_size"] >= body_size * 1.65 else 2
        previous = blocks[-1] if blocks else None
        merge = False
        if (
            previous
            and previous["type"] == kind == "paragraph"
            and previous["source"] == line["source"]
        ):
            last = previous["lines"][-1]
            height = max(1, last["bbox"][3] - last["bbox"][1])
            gap = line["bbox"][1] - last["bbox"][3]
            merge = (
                -0.2 * height <= gap <= 0.8 * height
                and abs(line["bbox"][0] - last["bbox"][0]) <= height * 1.5
                and last.get("group") == line.get("group")
                and not line.get("flags")
                and not last.get("flags")
            )
        if merge:
            previous["lines"].append(line)
            previous["bbox"] = rounded(union([previous["bbox"], line["bbox"]]))
            previous["text"] = join_lines(item_line["text"] for item_line in previous["lines"])
        else:
            blocks.append(
                {
                    "type": kind,
                    "heading_level": level,
                    "source": line["source"],
                    "bbox": line["bbox"],
                    "text": line["text"],
                    "lines": [line],
                }
            )
    for index, block in enumerate(blocks, 1):
        block["id"] = f"p{page_number:04d}-b{index:04d}"
        block["page"] = page_number
        block["reading_order"] = index - 1
        flags = sorted(
            set(
                block.get("flags", [])
                + [f for item_line in block["lines"] for f in item_line.get("flags", [])]
            )
        )
        scores = [
            item_line["confidence"]
            for item_line in block["lines"]
            if item_line.get("confidence") is not None
        ]
        block["quality"] = {
            "ocr_confidence": round(sum(scores) / len(scores), 4) if scores else None,
            "flags": flags,
            "needs_review": bool(flags),
        }
        block["structure_method"] = "rules"
        for line in block["lines"]:
            line.pop("group", None)
    return blocks, columns


def mark_running_headers(pages):
    """Mark repeated furniture without deleting it from either export."""
    candidates = {}
    for page in pages:
        for block in page["blocks"]:
            if block["type"] not in {"paragraph", "heading"} or len(block["text"]) > 120:
                continue
            y0, y1 = block["bbox"][1], block["bbox"][3]
            role = (
                "header"
                if y1 < page["height"] * 0.09
                else "footer"
                if y0 > page["height"] * 0.91
                else None
            )
            if role:
                text = normalized(block["text"])
                if re.fullmatch(r"(?:第)?\d+(?:页)?(?:/\d+)?", text):
                    text = "<page-number>"
                candidates.setdefault((role, text), []).append(block)
    threshold = max(3, math.ceil(len(pages) * 0.6))
    for (role, _), blocks in candidates.items():
        if len({b["page"] for b in blocks}) >= threshold:
            for block in blocks:
                block["role"] = role
