"""Regression checks for text loss, provenance, routing and optional dependencies."""

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pai_pdf.config import Options
from pai_pdf.export import markdown
from pai_pdf.layout import deduplicate, make_blocks, reading_order
from pai_pdf.parser import parse_document

ROOT = Path(__file__).resolve().parents[1]


def line(text, box, source="native", size=12, group=0):
    return {
        "text": text,
        "bbox": box,
        "source": source,
        "font_size": size,
        "confidence": 0.96 if source == "ocr" else None,
        "group": group,
        "flags": [],
    }


class StructureTests(unittest.TestCase):
    def test_duplicate_text_at_distinct_locations_is_preserved(self):
        native = line("100.00", [10, 10, 60, 25])
        same = line("100.00", [11, 10, 60, 25], "ocr")
        other_cell = line("100.00", [110, 10, 160, 25], "ocr")
        kept, _, removed = deduplicate([same, other_cell], [native])
        self.assertEqual(kept, [other_cell])
        self.assertEqual(removed, 1)

    def test_conflicting_ocr_is_preserved_and_flagged(self):
        native = line("100.00", [10, 10, 60, 25])
        ocr = line("900.00", [11, 10, 60, 25], "ocr")
        kept, conflicts, _ = deduplicate([ocr], [native])
        self.assertEqual(len(kept), 1)
        self.assertEqual(conflicts, 1)
        self.assertIn("source_text_conflict", kept[0]["flags"])

    def test_heading_followed_by_two_columns_reads_down_each_column(self):
        items = [
            {"name": name, "bbox": box}
            for name, box in [
                ("title", [20, 10, 580, 30]),
                ("L1", [20, 60, 250, 75]),
                ("R1", [330, 60, 580, 75]),
                ("L2", [20, 85, 250, 100]),
                ("R2", [330, 85, 580, 100]),
            ]
        ]
        ordered, columns = reading_order(items)
        self.assertEqual([i["name"] for i in ordered], ["title", "L1", "L2", "R1", "R2"])
        self.assertTrue(columns)

    def test_mixed_fonts_and_ocr_keep_native_confidence_unknown(self):
        lines = [
            line("Heading", [10, 10, 200, 35], size=24),
            line("A longer paragraph containing most of the document text.", [10, 50, 400, 65]),
            line("图片文字", [10, 100, 200, 120], "ocr", size=None),
        ]
        blocks, _ = make_blocks(lines, [], 1)
        self.assertEqual(blocks[0]["type"], "heading")
        self.assertIsNone(blocks[1]["quality"]["ocr_confidence"])
        self.assertEqual(blocks[2]["quality"]["ocr_confidence"], 0.96)
        self.assertEqual(blocks[2]["lines"][0]["bbox"], [10, 100, 200, 120])

    def test_markdown_keeps_literals_and_block_anchors(self):
        blocks, _ = make_blocks([line("<script> & [literal]", [10, 10, 200, 30])], [], 1)
        text = markdown(
            {"pages": [{"number": 1, "status": "success", "blocks": blocks, "images": []}]}
        )
        self.assertIn("&lt;script&gt; &amp; \\[literal\\]", text)
        self.assertIn("block:p0001-b0001", text)

    def test_importing_parser_does_not_load_models(self):
        code = "import sys; import pai_pdf.parser; assert not any(n in sys.modules for n in ('rapidocr','onnxruntime','torch','numpy','transformers','docling'))"
        subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True)


@unittest.skipUnless(importlib.util.find_spec("pymupdf"), "PyMuPDF 尚未安装，PDF 集成检查待运行")
class PdfIntegrationTests(unittest.TestCase):
    def setUp(self):
        import pymupdf

        self.fitz = pymupdf
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def parse(self, path, options=None):
        return parse_document(
            path,
            self.root / "out",
            options or Options(),
            Path(os.environ.get("PAI_OCR_MODELS", ROOT / ".cache/rapidocr")),
        )

    def native_pdf(self, count=1):
        path = self.root / "native.pdf"
        with self.fitz.open() as doc:
            for i in range(count):
                page = doc.new_page()
                page.insert_text((50, 80), f"Page {i + 1}: native content", fontsize=14)
            doc.save(path)
        return path

    def test_default_processes_more_than_twenty_pages_without_ocr(self):
        path = self.native_pdf(23)
        with patch(
            "pai_pdf.ocr.OcrEngine.recognize", side_effect=AssertionError("OCR must not run")
        ):
            result = self.parse(path)
        self.assertEqual(result["status"], "success")
        self.assertEqual(result["pages_processed"], 23)
        self.assertFalse(result["truncated"])
        self.assertFalse(result["engine"]["ocr_model_loaded"])

    def test_explicit_page_limit_is_visible(self):
        result = self.parse(self.native_pdf(3), Options(max_pages=1))
        self.assertTrue(result["truncated"])
        self.assertEqual(result["page_count"], 3)
        self.assertEqual(result["pages_processed"], 1)

    def test_rotation_and_crop_keep_native_coordinates_in_bounds(self):
        path = self.root / "rotated.pdf"
        with self.fitz.open() as doc:
            page = doc.new_page(width=600, height=800)
            page.insert_text((100, 120), "Locate this text", fontsize=14)
            page.set_cropbox(self.fitz.Rect(40, 40, 560, 760))
            page.set_rotation(90)
            doc.save(path)
        result = self.parse(path)
        page = result["pages"][0]
        self.assertEqual(page["original_rotation"], 90)
        self.assertEqual((page["width"], page["height"]), (520, 720))
        self.assertAlmostEqual(page["blocks"][0]["bbox"][0], 60, places=1)
        with self.fitz.open(path) as original:
            self.assertEqual(original[0].rotation, 90)

    def test_native_ruled_table_keeps_cell_content(self):
        result = self.parse(ROOT / "examples/sample.pdf", Options(ocr="off"))
        self.assertEqual(result["status"], "success")
        tables = [b for b in result["pages"][0]["blocks"] if b["type"] == "table"]
        self.assertTrue(tables)
        self.assertIn("Markdown", str(tables[0]["rows"]))
        self.assertIn("JSON", str(tables[0]["rows"]))

    def test_scan_ocr_off_flags_missing_text(self):
        path = self.root / "scan.pdf"
        with self.fitz.open(ROOT / "examples/sample.pdf") as source:
            image = source[0].get_pixmap().tobytes("png")
        with self.fitz.open() as doc:
            page = doc.new_page()
            page.insert_image(page.rect, stream=image)
            doc.save(path)
        result = self.parse(path, Options(ocr="off"))
        self.assertFalse(result["engine"]["ocr_model_loaded"])
        self.assertTrue(result["pages"][0]["quality"]["needs_review"])
        self.assertIn("ocr_disabled", str(result["pages"][0]["quality"]["warnings"]))

    def test_ocr_failure_keeps_native_text_and_partial_status(self):
        path = self.root / "mixed.pdf"
        with self.fitz.open(ROOT / "examples/sample.pdf") as source:
            image = source[0].get_pixmap().tobytes("png")
        with self.fitz.open() as doc:
            page = doc.new_page()
            page.insert_text((50, 40), "Native survives")
            page.insert_image(self.fitz.Rect(50, 100, 400, 600), stream=image)
            doc.save(path)
        with patch(
            "pai_pdf.ocr.OcrEngine.recognize", side_effect=RuntimeError("model unavailable")
        ):
            result = self.parse(path)
        self.assertEqual(result["status"], "partial_success")
        self.assertIn("Native survives", str(result["pages"][0]["blocks"]))

    def test_mixed_ocr_region_coordinates(self):
        """Offline integration check with real OCR; needs locally cached models."""
        models = Path(os.environ.get("PAI_OCR_MODELS", ROOT / ".cache/rapidocr"))
        if not (models / "PP-OCRv6_rec_small.onnx").exists() or not importlib.util.find_spec(
            "rapidocr"
        ):
            self.skipTest("Local OCR artifacts not available")
        path = self.root / "mixed-ocr.pdf"
        with self.fitz.open() as source:
            p = source.new_page(width=300, height=100)
            p.insert_text((20, 50), "REGION OCR 12345", fontsize=18)
            image = p.get_pixmap(matrix=self.fitz.Matrix(2, 2)).tobytes("png")
        with self.fitz.open() as doc:
            page = doc.new_page()
            page.insert_text((40, 50), "Native title")
            page.insert_image(self.fitz.Rect(80, 200, 380, 300), stream=image)
            page.set_rotation(90)
            doc.save(path)
        result = self.parse(path)
        self.assertEqual(result["status"], "success")
        ocr_lines = [
            item_line
            for b in result["pages"][0]["blocks"]
            for item_line in b["lines"]
            if item_line["source"] == "ocr"
        ]
        self.assertTrue(ocr_lines)
        self.assertIn("12345", " ".join(item_line["text"] for item_line in ocr_lines))
        for item_line in ocr_lines:
            x0, y0, x1, y1 = item_line["bbox"]
            self.assertTrue(80 <= x0 < x1 <= 380)
            self.assertTrue(200 <= y0 < y1 <= 300)


if __name__ == "__main__":
    unittest.main()
