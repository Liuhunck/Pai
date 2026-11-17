"""Small public API; the CLI and Python integrations share the same pipeline."""

from pathlib import Path

from .config import Options
from .export import write_outputs
from .ocr import OcrProvider
from .parser import parse_document


def convert(
    source: str | Path,
    output_dir: str | Path,
    *,
    options: Options | None = None,
    model_dir: str | Path | None = None,
    ocr_engine: OcrProvider | None = None,
) -> dict:
    """Convert a PDF into an empty output directory and return its document dict.

    Existing nonempty directories are rejected to protect earlier output. Page
    failures are returned in the document status; invalid inputs raise exceptions.
    """
    source, destination = Path(source), Path(output_dir)
    if not source.is_file():
        raise FileNotFoundError(source)
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise FileExistsError(f"Output directory must be empty: {destination}")
    document = parse_document(
        source,
        destination,
        options or Options(),
        model_dir,
        ocr_engine=ocr_engine,
    )
    write_outputs(document, destination)
    return document
