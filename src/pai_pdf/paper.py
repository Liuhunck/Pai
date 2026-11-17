"""Conservative paper semantics applied to ordered blocks, without rewriting text."""

import re

NAMED_SECTIONS = {
    "abstract",
    "摘要",
    "introduction",
    "引言",
    "background",
    "related work",
    "methods",
    "method",
    "methodology",
    "experiments",
    "results",
    "discussion",
    "conclusion",
    "conclusions",
    "结论",
    "references",
    "bibliography",
    "参考文献",
    "acknowledgments",
    "acknowledgements",
    "appendix",
}
REFERENCES = {"references", "bibliography", "参考文献"}
NUMBERED = re.compile(r"^(\d+(?:\.\d+)*)(?:\.)?\s+([A-Za-z\u3400-\u9fff].*)$")
CAPTION = re.compile(r"^(?:fig(?:ure)?\.?|table|图|表)\s*\d+[A-Za-z]?(?:[.:：\s]|$)", re.I)


def heading_level(text, *, prominent=False):
    """Infer familiar section names, and numbered headings with font evidence."""
    stripped = text.strip().rstrip(":：").casefold()
    if stripped in NAMED_SECTIONS:
        return 2
    match = NUMBERED.match(text.strip())
    if match and len(text) <= 100 and (prominent or match[2].casefold() in NAMED_SECTIONS):
        return min(6, match[1].count(".") + 2)
    return None


def annotate_paper(pages):
    """Add section paths and caption/reference roles; retain every source block."""
    sections = []
    in_references = False
    for page in pages:
        for block in page["blocks"]:
            if block.get("role") in {"header", "footer"}:
                continue
            text = block["text"].strip()
            if block["type"] != "table":
                level = heading_level(text, prominent=block["type"] == "heading")
                if level:
                    block["type"], block["heading_level"] = "heading", level
                elif CAPTION.match(text):
                    block["type"] = "caption"
                    block["heading_level"] = None
            if block["type"] == "heading":
                level = block["heading_level"]
                while sections and sections[-1][0] >= level:
                    sections.pop()
                sections.append((level, text))
                name = re.sub(r"^\d+(?:\.\d+)*\.?\s+", "", text).strip().casefold()
                in_references = name.rstrip(":：") in REFERENCES
            elif in_references:
                block["role"] = "reference"
            block["section_path"] = [title for _, title in sections]
