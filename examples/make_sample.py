"""Create a small born-digital PDF without third-party dependencies."""

from pathlib import Path

content = b"""BT /F1 22 Tf 50 780 Td (PDF parsing demo) Tj ET
BT /F1 13 Tf 50 740 Td (This is a locally generated sample document.) Tj ET
BT /F1 13 Tf 50 716 Td (Pai should preserve text and source locations.) Tj ET
BT /F1 17 Tf 50 665 Td (Project requirements) Tj ET
BT /F1 12 Tf 50 635 Td (1. Export Markdown and structured JSON.) Tj ET
BT /F1 12 Tf 50 615 Td (2. Run on CPU without a generative language model.) Tj ET
BT /F1 12 Tf 50 595 Td (3. Keep page numbers and bounding boxes.) Tj ET
BT /F1 12 Tf 50 540 Td (Format) Tj 200 0 Td (Purpose) Tj ET
BT /F1 12 Tf 50 510 Td (Markdown) Tj 200 0 Td (Reading and retrieval) Tj ET
BT /F1 12 Tf 50 480 Td (JSON) Tj 200 0 Td (Structure and provenance) Tj ET
40 560 m 530 560 l 530 460 l 40 460 l h S
40 530 m 530 530 l S 40 500 m 530 500 l S 230 560 m 230 460 l S
"""
objects = [
    b"<< /Type /Catalog /Pages 2 0 R >>",
    b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"endstream",
]
pdf = bytearray(b"%PDF-1.4\n")
offsets = [0]
for i, obj in enumerate(objects, 1):
    offsets.append(len(pdf))
    pdf.extend(f"{i} 0 obj\n".encode() + obj + b"\nendobj\n")
xref = len(pdf)
pdf.extend(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
for offset in offsets[1:]:
    pdf.extend(f"{offset:010d} 00000 n \n".encode())
pdf.extend(
    f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
)
path = Path(__file__).with_name("sample.pdf")
path.write_bytes(pdf)
print(path)
