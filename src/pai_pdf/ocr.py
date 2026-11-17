"""Lazy CPU OCR. Importing this module does not load numpy, ONNX or models."""

import os
from pathlib import Path
from typing import Protocol

from .layout import rounded


class OcrProvider(Protocol):
    """Injectable OCR adapter; coordinates must be unrotated page points."""

    calls: int

    @property
    def loaded(self) -> bool: ...

    def recognize(self, png: bytes, origin, scale: float, bounds) -> list[dict]: ...


class OcrEngine:
    def __init__(self, model_dir=None, threads=2):
        cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        self.model_dir = Path(model_dir) if model_dir else cache / "pai" / "rapidocr"
        self.threads = threads
        self.engine = None
        self.calls = 0

    @property
    def loaded(self):
        return self.engine is not None

    def recognize(self, png, origin, scale, bounds):
        if self.engine is None:
            try:
                import onnxruntime
                from rapidocr import RapidOCR
            except ImportError as exc:
                raise RuntimeError(
                    'OCR dependencies missing; from the Pai checkout run: pip install -e ".[ocr]"'
                ) from exc
            onnxruntime.disable_telemetry_events()
            self.model_dir.mkdir(parents=True, exist_ok=True)
            params = {
                "Global.model_root_dir": str(self.model_dir),
                "Global.log_level": "warning",
                "EngineConfig.onnxruntime.intra_op_num_threads": self.threads,
                "EngineConfig.onnxruntime.inter_op_num_threads": 1,
                "EngineConfig.onnxruntime.use_cuda": False,
                "EngineConfig.onnxruntime.use_dml": False,
                "EngineConfig.onnxruntime.use_coreml": False,
            }
            names = {
                "Det": "PP-OCRv6_det_small.onnx",
                "Rec": "PP-OCRv6_rec_small.onnx",
                "Cls": "ch_ppocr_mobile_v2.0_cls_mobile.onnx",
            }
            for kind, name in names.items():
                if (self.model_dir / name).exists():
                    params[f"{kind}.model_path"] = str(self.model_dir / name)
            self.engine = RapidOCR(params=params)
        self.calls += 1
        result = self.engine(png)
        if result.boxes is None or result.txts is None:
            return []
        lines = []
        for box, text, score in zip(result.boxes, result.txts, result.scores):
            polygon = [
                [
                    max(bounds[0], min(bounds[2], (float(x) + origin[0]) / scale)),
                    max(bounds[1], min(bounds[3], (float(y) + origin[1]) / scale)),
                ]
                for x, y in box
            ]
            if not text.strip():
                continue
            bbox = [
                min(p[0] for p in polygon),
                min(p[1] for p in polygon),
                max(p[0] for p in polygon),
                max(p[1] for p in polygon),
            ]
            lines.append(
                {
                    "text": text,
                    "bbox": rounded(bbox),
                    "polygon": [rounded(p) for p in polygon],
                    "source": "ocr",
                    "confidence": round(float(score), 4),
                    "group": "ocr",
                    "font_size": None,
                    "flags": ["low_ocr_confidence"] if score < 0.8 else [],
                }
            )
        return lines
