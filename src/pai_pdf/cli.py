"""Command line entry point for the lightweight PDF parser."""

import argparse
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

from pai_pdf import __version__
from pai_pdf.config import Options
from pai_pdf.export import write_outputs
from pai_pdf.parser import parse_document


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="轻量 PDF 解析：PyMuPDF＋按需 RapidOCR，默认处理整个文件"
    )
    parser.add_argument("pdf", type=Path, help="本地 PDF 路径")
    parser.add_argument(
        "--output", type=Path, default=Path("output"), help="输出根目录，每次创建独立子目录"
    )
    parser.add_argument(
        "--ocr",
        choices=["auto", "off", "force"],
        default="auto",
        help="auto 按需识字；off 完全不用模型；force 整页识字",
    )
    parser.add_argument("--max-pages", type=int, help="只处理前 N 页，不指定则处理全部页面")
    parser.add_argument("--dpi", type=int, default=180, help="OCR 渲染 DPI，默认 180")
    parser.add_argument(
        "--max-pixels", type=int, default=6_000_000, help="单次 OCR 图像像素上限，默认 600 万"
    )
    parser.add_argument("--threads", type=int, default=2, help="OCR CPU 线程数，默认 2")
    parser.add_argument("--no-tables", action="store_true", help="关闭基于表格线的提取")
    parser.add_argument("--no-images", action="store_true", help="不导出图片资源，不影响 OCR")
    parser.add_argument("--models", type=Path, default=None, help="OCR 模型目录")
    parser.add_argument("--version", action="version", version="%(prog)s " + __version__)
    args = parser.parse_args(argv)
    source = args.pdf.expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".pdf":
        parser.error("请提供存在的本地 PDF 文件")
    if (
        (args.max_pages is not None and args.max_pages < 1)
        or args.dpi < 1
        or args.max_pixels < 1
        or args.threads < 1
    ):
        parser.error("页数、DPI、像素上限和线程数必须为正数")
    if importlib.util.find_spec("pymupdf") is None:
        print("缺少 PyMuPDF，请在 Pai 仓库执行：pip install -e .", file=sys.stderr)
        return 1
    args.output.mkdir(parents=True, exist_ok=True)
    destination = Path(tempfile.mkdtemp(prefix=f"{source.stem[:60]}-", dir=args.output))
    options = Options(
        ocr=args.ocr,
        max_pages=args.max_pages,
        dpi=args.dpi,
        max_pixels=args.max_pixels,
        threads=args.threads,
        tables=not args.no_tables,
        images=not args.no_images,
    )
    try:
        document = parse_document(
            source,
            destination,
            options,
            args.models.expanduser() if args.models else None,
            progress=lambda n, total, status: print(f"[{n}/{total}] {status}", file=sys.stderr),
        )
        try:
            import resource

            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            peak = round(rss / (1024**2 if sys.platform == "darwin" else 1024), 1)
        except ImportError:
            peak = None
        write_outputs(document, destination, peak)
        print(
            f"状态：{document['status']}；处理 {document['pages_processed']}/{document['page_count']} 页"
        )
        print(
            f"耗时：{document['elapsed_seconds']} 秒；OCR 调用：{document['engine']['ocr_calls']} 次"
        )
        print(f"结果目录：{destination}")
        return 0 if document["status"] == "success" else 2
    except Exception as exc:
        (destination / "report.json").write_text(
            json.dumps({"status": "failure", "error": str(exc)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"解析失败：{exc}\n报告目录：{destination}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
