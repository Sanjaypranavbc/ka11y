import threading
from typing import Optional

import easyocr

# ---------------------------------------------------------------------------
# Module-level singleton — EasyOCR models (~200 MB) are loaded once per
# process rather than once per OCRReader instance. Double-checked locking
# ensures thread safety without holding the lock on every readtext() call.
# ---------------------------------------------------------------------------
_reader: Optional[easyocr.Reader] = None
_reader_lock = threading.Lock()


def get_ocr_reader(lang: str = "en") -> easyocr.Reader:
    """Return the shared EasyOCR Reader, initialising it on first call."""
    global _reader
    # Map supported languages to EasyOCR codes.
    # For Japanese, we need both 'en' and 'ja' to handle mixed text.
    langs = ["en"]
    if lang in ("ja", "jp"):
        langs.append("ja")

    if _reader is None:
        with _reader_lock:
            if _reader is None:
                _reader = easyocr.Reader(langs, gpu=False, verbose=False)
    return _reader


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
