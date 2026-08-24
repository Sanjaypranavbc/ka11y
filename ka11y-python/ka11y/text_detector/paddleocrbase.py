import os
import threading
from typing import Optional

# Suppress PaddleOCR's connectivity check to model-hosting servers on startup.
# Models are downloaded on first use; this only skips the upfront ping.
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

try:
    from paddleocr import PaddleOCR
except ImportError:
    # If the user hasn't installed paddleocr, this file will still import
    # but get_ocr_reader will fail gracefully.
    PaddleOCR = None

# ---------------------------------------------------------------------------
# Thread-local reader cache — PaddleOCR models are loaded once per *thread*
# rather than once per process, mirroring ocrbase.py. text_detector's
# scan_directory() runs OCR for multiple images concurrently via a worker
# thread pool, and PaddleOCR gives no guarantee that a shared instance is
# safe to call concurrently from multiple threads — each worker thread gets
# and keeps its own instance instead.
# ---------------------------------------------------------------------------
_thread_local = threading.local()


def get_ocr_reader(lang: str = "en") -> Optional[PaddleOCR]:
    """Return this thread's PaddleOCR instance, initialising it on first use."""
    if PaddleOCR is None:
        return None

    # Map requested language to PaddleOCR's internal codes
    # PaddleOCR uses 'japan' for Japanese.
    paddle_lang = lang
    if lang in ("ja", "jp"):
        paddle_lang = "japan"

    readers = getattr(_thread_local, "readers", None)
    if readers is None:
        readers = {}
        _thread_local.readers = readers
    if paddle_lang not in readers:
        readers[paddle_lang] = PaddleOCR(lang=paddle_lang)
    return readers[paddle_lang]


class OCRReader:
    """
    Drop-in replacement for the EasyOCR-backed OCRReader.

    The public interface is identical:
        reader = OCRReader(source_directory)
        detections = reader.readtext(image_path)

    readtext() returns a list of (bbox, text, confidence) tuples so that all
    downstream code in text_detector.py that unpacks ``for bbox, text, conf``
    continues to work unchanged.

    PaddleOCR v3 bbox format: a list of four [x, y] points
        [[x0,y0], [x1,y1], [x2,y2], [x3,y3]]
    EasyOCR bbox format: a list of four (x, y) tuples — same shape.
    Both represent the four corners of the detected text region, so the
    existing ``clean_bbox = [(int(p[0]), int(p[1])) for p in bbox]`` line in
    text_detector.py works with either engine without modification.
    """

    def __init__(
        self,
        source_directory: str,
        output_directory: Optional[str] = None,
        lang: str = "en",
    ):
        self.source_directory = source_directory
        self.output_directory = output_directory
        self.lang = lang

    @property
    def reader(self) -> Optional[PaddleOCR]:
        """Lazily return the singleton PaddleOCR instance."""
        return get_ocr_reader(self.lang)

    def readtext(self, image_path: str):
        """
        Run OCR on *image_path* and return results in EasyOCR-compatible format.

        Returns
        -------
        list of (bbox, text, confidence)
            bbox       – list of four (x, y) int tuples (TL, TR, BR, BL)
            text       – recognised string
            confidence – float in [0, 1]
        """
        reader = self.reader
        if reader is None:
            raise RuntimeError("PaddleOCR is not installed.")
        raw = reader.predict(image_path)

        results = []
        # predict() returns a list with one dict per image.
        for page in raw:
            boxes = page.get("dt_polys", [])  # list of np arrays, shape (4, 2)
            texts = page.get("rec_texts", [])
            scores = page.get("rec_scores", [])

            for box, text, score in zip(boxes, texts, scores):
                # Convert numpy int64 corners → plain Python (x, y) tuples
                bbox = [(int(pt[0]), int(pt[1])) for pt in box]
                results.append((bbox, text, float(score)))

        return results
