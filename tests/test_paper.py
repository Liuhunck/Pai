"""Paper structure and AI chunk provenance regressions."""

import unittest

from test_core import line

from pai_pdf.chunking import chunk_document
from pai_pdf.config import Options
from pai_pdf.layout import make_blocks, mark_running_headers
from pai_pdf.paper import annotate_paper


class PaperTests(unittest.TestCase):
    def document(self, lines):
        blocks, _ = make_blocks(lines, [], 1)
        pages = [{"number": 1, "height": 800, "blocks": blocks}]
        annotate_paper(pages)
        return {"document_id": "example-sha", "pages": pages}

    def test_sections_captions_and_references_do_not_merge_into_body(self):
        doc = self.document(
            [
                line("Abstract", [10, 10, 100, 22]),
                line("We evaluate scientific document extraction.", [10, 26, 300, 38]),
                line("1 Introduction", [10, 50, 150, 62]),
                line("The main contribution is a small parser.", [10, 66, 300, 78]),
                line("Figure 1. Extraction pipeline", [10, 82, 260, 94]),
                line("References", [10, 110, 100, 122]),
                line("[1] A. Author. A useful paper. 2025.", [10, 126, 300, 138]),
            ]
        )
        blocks = doc["pages"][0]["blocks"]
        self.assertEqual(
            [b["type"] for b in blocks],
            [
                "heading",
                "paragraph",
                "heading",
                "paragraph",
                "caption",
                "heading",
                "paragraph",
            ],
        )
        self.assertEqual(blocks[3]["section_path"], ["1 Introduction"])
        self.assertEqual(blocks[-1]["role"], "reference")

    def test_numbered_list_is_not_a_section_without_font_evidence(self):
        doc = self.document([line("1. Export all pages", [10, 10, 200, 22])])
        self.assertEqual(doc["pages"][0]["blocks"][0]["type"], "list_item")

    def test_nested_numbered_heading_with_bold_font(self):
        child = line("2.1 Our approach", [10, 40, 200, 52])
        child["bold"] = True
        doc = self.document([line("2 Methods", [10, 10, 200, 22]), child])
        self.assertEqual(
            doc["pages"][0]["blocks"][-1]["section_path"], ["2 Methods", "2.1 Our approach"]
        )

    def test_chunks_are_bounded_and_offsets_reconstruct_all_source_text(self):
        doc = self.document(
            [
                line("摘要", [10, 10, 100, 22]),
                line("中文内容" * 30, [10, 40, 300, 52]),
                line("1 Introduction", [10, 80, 200, 92]),
                line("A repeated sentence. " * 25, [10, 110, 400, 122]),
            ]
        )
        blocks = {b["id"]: b for b in doc["pages"][0]["blocks"]}
        for limit in (1, 17, 80, 1600):
            chunks = chunk_document(doc, max_chars=limit)
            reconstructed = {key: "" for key in blocks}
            for chunk in chunks:
                self.assertLessEqual(len(chunk["text"]), limit)
                parts = []
                for ref in chunk["sources"]:
                    block = blocks[ref["block_id"]]
                    part = block["text"][ref["start"] : ref["end"]]
                    reconstructed[block["id"]] += part
                    parts.append(part)
                    self.assertEqual(chunk["section_path"], block["section_path"])
                self.assertEqual(chunk["text"], "\n\n".join(parts))
            self.assertEqual(reconstructed, {key: b["text"] for key, b in blocks.items()})

    def test_running_headers_preserved_but_excluded_from_chunks(self):
        pages = []
        for n in range(1, 4):
            blocks, _ = make_blocks(
                [
                    line("Journal of Example", [10, 10, 200, 22]),
                    line(f"Unique body {n}", [10, 100, 200, 112]),
                    line(str(n), [10, 760, 30, 772]),
                ],
                [],
                n,
            )
            pages.append({"number": n, "height": 800, "blocks": blocks})
        mark_running_headers(pages)
        annotate_paper(pages)
        doc = {"document_id": "example", "pages": pages}
        self.assertEqual(pages[0]["blocks"][0]["role"], "header")
        self.assertNotIn("Journal", str(chunk_document(doc)))
        self.assertIn("Journal", str(chunk_document(doc, include_furniture=True)))

    def test_invalid_options_fail_before_processing(self):
        for kwargs in (
            {"ocr": "invalid"},
            {"max_pages": 0},
            {"dpi": float("nan")},
            {"threads": True},
        ):
            with self.assertRaises(ValueError):
                Options(**kwargs)
