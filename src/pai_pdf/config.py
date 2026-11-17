"""Validated, immutable extraction settings."""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Options:
    ocr: Literal["auto", "off", "force"] = "auto"
    max_pages: int | None = None
    dpi: int = 180
    max_pixels: int = 6_000_000
    threads: int = 2
    tables: bool = True
    images: bool = True

    def __post_init__(self):
        if self.ocr not in {"auto", "off", "force"}:
            raise ValueError("ocr must be auto, off or force")
        for name in ("max_pages", "dpi", "max_pixels", "threads"):
            value = getattr(self, name)
            if name == "max_pages" and value is None:
                continue
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
