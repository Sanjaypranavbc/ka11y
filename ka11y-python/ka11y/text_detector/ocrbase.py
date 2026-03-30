import threading
from typing import Optional

import easyocr

# ---------------------------------------------------------------------------
# Module-level cache — EasyOCR models are loaded once per language set
# rather than once per OCRReader instance.
# ---------------------------------------------------------------------------
_readers: dict[tuple[str, ...], easyocr.Reader] = {}
_reader_lock = threading.Lock()


def _normalize_langs(langs: Optional[list[str]]) -> tuple[str, ...]:
    values = tuple((langs or ["en"]))
    cleaned = tuple(s.strip().lower() for s in values if s and s.strip())
    return cleaned or ("en",)


def get_ocr_reader(langs: Optional[list[str]] = None) -> easyocr.Reader:
    """Return a shared EasyOCR reader for a specific language tuple."""
    key = _normalize_langs(langs)
    reader = _readers.get(key)
    if reader is not None:
        return reader

    with _reader_lock:
        reader = _readers.get(key)
        if reader is None:
            reader = easyocr.Reader(list(key), gpu=False, verbose=False)
            _readers[key] = reader
    return reader


class OCRReader:

    def __init__(
        self,
        source_directory: str,
        output_directory: Optional[str] = None,
        langs: Optional[list[str]] = None,
    ):
        self.source_directory = source_directory
        self.output_directory = output_directory
        self.langs = langs or ["en"]

    @property
    def reader(self) -> easyocr.Reader:
        """Lazily return the shared reader for this language set."""
        return get_ocr_reader(self.langs)

    def readtext(self, image_path: str):
        return self.reader.readtext(image_path)
