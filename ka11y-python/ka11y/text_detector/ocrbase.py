import threading
from typing import Optional

import easyocr

# ---------------------------------------------------------------------------
# Module-level singleton — EasyOCR models (~200 MB) are loaded once per
# process rather than once per OCRReader instance. Double-checked locking
# ensures thread safety without holding the lock on every readtext() call.
# ---------------------------------------------------------------------------
_readers: dict[str, easyocr.Reader] = {}
_reader_lock = threading.Lock()


def get_ocr_reader(lang: str = "en") -> easyocr.Reader:
    """Return the shared EasyOCR Reader, initialising it on first call."""
    global _readers
    # Map supported languages to EasyOCR codes.
    # For Japanese, we need both 'en' and 'ja' to handle mixed text.
    langs = ["en"]
    if lang in ("ja", "jp"):
        langs.append("ja")

    cache_key = "_".join(langs)

    if cache_key not in _readers:
        with _reader_lock:
            if cache_key not in _readers:
                _readers[cache_key] = easyocr.Reader(langs, gpu=False, verbose=False)
    return _readers[cache_key]


class OCRReader:

    def __init__(self, source_directory: str, output_directory: Optional[str] = None, lang: str = "en"):
        self.source_directory = source_directory
        self.output_directory = output_directory
        self.lang = lang

    @property
    def reader(self) -> easyocr.Reader:
        """Lazily return the singleton reader."""
        return get_ocr_reader(self.lang)

    # def readtext(self, image_path: str):
    #     return self.reader.readtext(image_path)

    def readtext(self, image_path: str):
        return self.reader.readtext(
            image_path,
            detail=1,
            paragraph=False,
            text_threshold=0.75,
            low_text=0.5,
            link_threshold=0.4
        )
