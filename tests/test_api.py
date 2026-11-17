"""Public API and installed CLI contract checks with real PDF files."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pymupdf

from pai_pdf import Options, convert


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "paper.pdf"
        with pymupdf.open() as doc:
            page = doc.new_page()
            page.insert_text((40, 50), "Abstract", fontsize=14)
            page.insert_text((40, 90), "A minimal paper for extraction.")
            doc.save(self.source)

    def tearDown(self):
        self.temp.cleanup()

    def test_public_api_exports_and_refuses_to_overwrite(self):
        destination = self.root / "result"
        result = convert(self.source, destination, options=Options(ocr="off"))
        self.assertEqual(result["status"], "success")
        for name in ("document.json", "document.md", "report.json", "chunks.jsonl"):
            self.assertTrue((destination / name).is_file())
        self.assertEqual(json.loads((destination / "document.json").read_text()), result)
        with self.assertRaises(FileExistsError):
            convert(self.source, destination)

    def test_native_two_column_paper_reads_down_each_column(self):
        paper = self.root / "two-columns.pdf"
        with pymupdf.open() as doc:
            page = doc.new_page(width=600, height=800)
            page.insert_text((40, 50), "A Scientific Paper with Two Columns", fontsize=24)
            # Deliberately write in row order: extraction must recover column order.
            for y, left, right in [
                (110, "Left first paragraph.", "Right first paragraph."),
                (140, "Left second paragraph.", "Right second paragraph."),
            ]:
                page.insert_text((40, y), left, fontsize=12)
                page.insert_text((330, y), right, fontsize=12)
            doc.save(paper)
        result = convert(paper, self.root / "columns", options=Options(ocr="off"))
        texts = [b["text"] for b in result["pages"][0]["blocks"]]
        self.assertEqual(
            texts,
            [
                "A Scientific Paper with Two Columns",
                "Left first paragraph.",
                "Left second paragraph.",
                "Right first paragraph.",
                "Right second paragraph.",
            ],
        )

    def test_conversion_does_not_import_inference_runtimes(self):
        code = (
            "import sys; from pai_pdf import convert; "
            "convert(sys.argv[1], sys.argv[2]); "
            "assert not any(n in sys.modules for n in "
            "('rapidocr', 'onnxruntime', 'torch', 'numpy', 'transformers', 'docling'))"
        )
        subprocess.run(
            [sys.executable, "-c", code, str(self.source), str(self.root / "native")], check=True
        )

    def test_cli_unique_outputs_and_failure_exit_code(self):
        command = [
            sys.executable,
            "-m",
            "pai_pdf",
            str(self.source),
            "--ocr",
            "off",
            "--output",
            str(self.root / "out"),
        ]
        for _ in range(2):
            run = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(len(list((self.root / "out").iterdir())), 2)
        run = subprocess.run(command + ["--max-pages", "0"], capture_output=True)
        self.assertEqual(run.returncode, 2)

    def test_encrypted_and_invalid_pdf_are_explicit_errors(self):
        encrypted = self.root / "encrypted.pdf"
        with pymupdf.open(self.source) as doc:
            doc.save(
                encrypted,
                encryption=pymupdf.PDF_ENCRYPT_AES_256,
                user_pw="secret",
                owner_pw="owner",
            )
        with self.assertRaisesRegex(ValueError, "已加密"):
            convert(encrypted, self.root / "encrypted-out")
        invalid = self.root / "invalid.pdf"
        invalid.write_text("not a pdf")
        with self.assertRaises(pymupdf.FileDataError):
            convert(invalid, self.root / "invalid-out")

    def test_injected_ocr_provider_preserves_source_and_coordinates(self):
        class FakeOcr:
            loaded = True
            calls = 0

            def recognize(self, png, origin, scale, bounds):
                self.calls += 1
                return [
                    {
                        "text": "Recognized text",
                        "bbox": [40, 40, 200, 60],
                        "source": "ocr",
                        "confidence": 0.9,
                        "font_size": None,
                        "flags": [],
                    }
                ]

        result = convert(
            self.source, self.root / "injected", options=Options(ocr="force"), ocr_engine=FakeOcr()
        )
        self.assertEqual(result["engine"]["ocr_calls"], 1)
        page = result["pages"][0]
        self.assertEqual(page["blocks"][0]["text"], "Recognized text")
        self.assertTrue(page["raw_native_lines"])
