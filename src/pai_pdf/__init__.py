"""Lightweight, local PDF extraction. No model is imported at package import."""

__version__ = "0.1.0"

# Lazy exports keep package import free of PDF engines and inference runtimes.
__all__ = ["Options", "convert", "__version__"]


def __getattr__(name):
    if name == "Options":
        from .config import Options

        return Options
    if name == "convert":
        from .api import convert

        return convert
    raise AttributeError(name)
