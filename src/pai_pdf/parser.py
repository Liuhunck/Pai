"""Coordinate extraction stages and preserve partial results on page failure."""

import hashlib
import importlib.metadata
import time
from dataclasses import asdict
from pathlib import Path

from . import __version__
from .backends.pymupdf import extract_tables, image_regions, native_lines, render
from .config import Options
from .layout import (
    area,
    bad_text_ratio,
    deduplicate,
    intersection,
    make_blocks,
    mark_running_headers,
    rounded,
    union,
)
from .ocr import OcrEngine, OcrProvider
from .paper import annotate_paper


def _covered_by_text(box, native, page_area):
    # Only skip OCR for near-full-page scans with a substantial existing text layer.
    if area(box) < page_area * 0.75:
        return False
    inside = [
        item_line
        for item_line in native
        if area(intersection(item_line["bbox"], box)) / max(1, area(item_line["bbox"])) > 0.8
    ]
    if len(inside) < 8 or sum(len(item_line["text"]) for item_line in inside) < 150:
        return False
    coverage = union([item_line["bbox"] for item_line in inside])
    return (coverage[3] - coverage[1]) / max(1, box[3] - box[1]) > 0.6 and bad_text_ratio(
        "".join(item_line["text"] for item_line in inside)
    ) <= 0.03


def _parse_page(page, options, engine, asset_dir, fitz):
    number, rotation = page.number + 1, page.rotation
    # PyMuPDF text coordinates are unrotated. Render in exactly the same space.
    # This change is in-memory only: the source PDF is never saved or overwritten.
    page.set_rotation(0)
    start = time.perf_counter()
    try:
        bounds = list(page.rect)
        native, removed = native_lines(page, fitz)
        images = image_regions(page)
        raw_text = "\n".join(item_line["text"] for item_line in native)
        warnings, errors, routes = [], [], []
        tables = []
        bad_native = bad_text_ratio(raw_text) > 0.03
        blank = not native and not images and not page.get_drawings()
        full_ocr = options.ocr == "force" or bad_native or (not native and not blank)
        ocr_disabled = options.ocr == "off"
        targets = []
        if not ocr_disabled:
            if full_ocr and not blank:
                targets = [bounds]
            elif not blank:
                for box in images:
                    if _covered_by_text(box, native, area(bounds)):
                        routes.append({"bbox": rounded(box), "action": "use_existing_text_layer"})
                    else:
                        targets.append(box)
        elif images or full_ocr:
            warnings.append({"code": "ocr_disabled", "detail": "图片或异常文字层未经 OCR 验证。"})
        recognized = []
        calls_before = engine.calls
        for index, box in enumerate(targets):
            route = {"bbox": rounded(box), "action": "full_page_ocr" if full_ocr else "region_ocr"}
            routes.append(route)
            try:
                png, origin, scale = render(page, box, options, fitz)
                lines = engine.recognize(png, origin, scale, bounds)
                for line in lines:
                    line["group"] = f"ocr-{index}"
                recognized.extend(lines)
                route["lines_found"] = len(lines)
                route["render_dpi"] = round(scale * 72, 2)
                if scale * 72 < options.dpi - 1:
                    warnings.append(
                        {
                            "code": "render_resolution_limited",
                            "detail": "按像素上限降低了 OCR 渲染分辨率。",
                        }
                    )
            except Exception as exc:
                route["error"] = str(exc)
                errors.append({"code": "ocr_failed", "bbox": rounded(box), "detail": str(exc)})
        if targets:
            warnings.append(
                {
                    "code": "ocr_structure_unverified",
                    "detail": "OCR 区域的表格、公式和段落结构未使用模型恢复。",
                }
            )
        if full_ocr and recognized:
            selected, conflicts, extra_removed = deduplicate(recognized)
            if native:
                warnings.append(
                    {
                        "code": "native_text_replaced",
                        "detail": "采用整页 OCR；原始文字行另存 raw_native_lines。",
                    }
                )
        else:
            supplement, conflicts, extra_removed = deduplicate(recognized, native)
            selected = native + supplement
            if full_ocr and not blank and not recognized:
                warnings.append(
                    {
                        "code": "no_ocr_text",
                        "detail": "未得到 OCR 文字；保留原生提取结果，可能是图片页或识别遗漏。",
                    }
                )
            if options.tables and native and not bad_native:
                tables, table_warnings = extract_tables(page, native)
                warnings.extend(table_warnings)
                absorbed = {id(line) for table in tables for line in table["lines"]}
                selected = [line for line in selected if id(line) not in absorbed]
        if conflicts:
            warnings.append(
                {
                    "code": "source_text_conflict",
                    "detail": f"{conflicts} 处原生文字与 OCR 不一致，保留待复核。",
                }
            )
        if bad_native:
            warnings.append({"code": "suspicious_text_layer", "detail": "原生文字含较多异常字符。"})
        blocks, columns = make_blocks(selected, tables, number)
        if columns:
            warnings.append(
                {
                    "code": "column_order_inferred",
                    "detail": "根据空白分栏推断阅读顺序，请抽查复杂排版。",
                }
            )
        image_records = []
        for index, box in enumerate(images, 1):
            record = {"id": f"p{number:04d}-img{index:04d}", "bbox": rounded(box), "asset": None}
            # Do not duplicate an entire scan as a figure in the Markdown output.
            is_scan_background = area(box) > area(bounds) * 0.75
            record["role"] = "page_background" if is_scan_background else "figure"
            if options.images and not is_scan_background:
                try:
                    png, _, _ = render(page, box, options, fitz)
                    name = record["id"] + ".png"
                    asset_dir.mkdir(parents=True, exist_ok=True)
                    (asset_dir / name).write_bytes(png)
                    record["asset"] = f"assets/{name}"
                except Exception as exc:
                    errors.append({"code": "image_export_failed", "detail": str(exc)})
            image_records.append(record)
        status = "partial_success" if errors else "success"
        if errors and not blocks:
            status = "failure"
        result = {
            "number": number,
            "width": page.rect.width,
            "height": page.rect.height,
            "original_rotation": rotation,
            "cropbox": rounded(page.cropbox),
            "type": "blank"
            if blank
            else "mixed"
            if native and images
            else "digital"
            if native
            else "scanned_or_graphics",
            "status": status,
            "blocks": blocks,
            "images": image_records,
            "quality": {
                "needs_review": bool(
                    errors or warnings or any(b["quality"]["needs_review"] for b in blocks)
                ),
                "warnings": warnings,
                "errors": errors,
                "native_bad_character_ratio": round(bad_text_ratio(raw_text), 4),
            },
            "processing": {
                "routes": routes,
                "ocr_calls": engine.calls - calls_before,
                "duplicate_lines_removed": removed + extra_removed,
                "elapsed_seconds": round(time.perf_counter() - start, 3),
            },
        }
        if full_ocr and native:
            result["raw_native_lines"] = native
        return result
    finally:
        page.set_rotation(rotation)


def parse_document(
    source: str | Path,
    destination: str | Path,
    options: Options,
    model_dir: str | Path | None = None,
    progress=None,
    ocr_engine: OcrProvider | None = None,
) -> dict:
    import pymupdf as fitz

    source, destination = Path(source), Path(destination)
    with source.open("rb") as stream:
        sha = hashlib.file_digest(stream, "sha256").hexdigest()
    engine = ocr_engine if ocr_engine is not None else OcrEngine(model_dir, options.threads)
    start = time.perf_counter()
    with fitz.open(source) as doc:
        if not doc.is_pdf:
            raise ValueError("文件不是 PDF")
        if doc.needs_pass:
            raise ValueError("PDF 已加密，请先使用密码解锁后再解析")
        total = len(doc)
        count = min(total, options.max_pages) if options.max_pages is not None else total
        pages = []
        for index in range(count):
            try:
                item = _parse_page(doc[index], options, engine, destination / "assets", fitz)
            except Exception as exc:
                page = doc[index]
                unrotated = page.rect * page.derotation_matrix
                item = {
                    "number": index + 1,
                    "width": unrotated.width,
                    "height": unrotated.height,
                    "original_rotation": page.rotation,
                    "status": "failure",
                    "type": "unknown",
                    "blocks": [],
                    "images": [],
                    "quality": {
                        "needs_review": True,
                        "warnings": [],
                        "errors": [{"code": "page_failed", "detail": str(exc)}],
                    },
                    "processing": {"ocr_calls": 0},
                }
            pages.append(item)
            if progress:
                progress(index + 1, count, item["status"])
        metadata = doc.metadata
    mark_running_headers(pages)
    annotate_paper(pages)
    status = "success"
    if not pages or all(p["status"] == "failure" for p in pages):
        status = "failure"
    elif any(p["status"] != "success" for p in pages):
        status = "partial_success"
    versions = {"pai_pdf": __version__, "pymupdf": fitz.VersionBind}
    for package in ("rapidocr", "onnxruntime"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return {
        "schema_version": "1.0.0",
        "document_id": sha,
        "source": {"path": str(source.resolve()), "sha256": sha},
        "metadata": metadata,
        "page_count": total,
        "pages_processed": count,
        "truncated": count < total,
        "status": status,
        "coordinates": {
            "origin": "top-left of unrotated visible page",
            "unit": "pt",
            "points_per_inch": 72,
            "bbox": "[x0, y0, x1, y1]",
            "page_numbers": "1-based",
        },
        "engine": {
            "name": "pai",
            "backend": "pymupdf",
            "ocr_provider": type(engine).__name__,
            "versions": versions,
            "device": "cpu",
            "generative_models": False,
            "layout_models": False,
            "table_models": False,
            "ocr_model_loaded": engine.loaded,
            "ocr_calls": engine.calls,
        },
        "options": asdict(options),
        "elapsed_seconds": round(time.perf_counter() - start, 3),
        "pages": pages,
    }
