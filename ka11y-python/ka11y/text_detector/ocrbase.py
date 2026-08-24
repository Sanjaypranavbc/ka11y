import threading
from typing import Optional

import easyocr
import torch

# EasyOCR's CPU backend uses PyTorch's intra-op thread pool (torch.
# get_num_threads(), often == CPU count) *within a single* readtext() call.
# text_detector.scan_directory() now also parallelizes *across* images via a
# worker thread pool (see _get_ocr_executor there) — left at its default,
# every one of those workers would additionally fan out across all CPUs for
# its own call, oversubscribing the box (N workers x M intra-op threads) and
# eating most of the wall-clock win the worker pool is meant to provide.
# Capping intra-op parallelism to 1 hands control entirely to the worker
# pool, which is what actually gives close-to-linear speedup for a "many
# small independent images" workload like this one. Safe to call at import
# time: EasyOCR's Reader construction does not touch this setting itself,
# so it isn't reset by a later `easyocr.Reader(...)` call.
torch.set_num_threads(1)

# ---------------------------------------------------------------------------
# Thread-local reader cache — EasyOCR models (~200 MB) are loaded once per
# *thread* rather than once per process. text_detector.scan_directory() now
# runs OCR for multiple images concurrently via a worker thread pool, and
# Reader.readtext() has no documented guarantee of being safe to call
# concurrently from multiple threads against one shared instance. Each
# worker thread therefore gets and keeps its own Reader, exactly the same
# amortization a single process-wide singleton gave a single-threaded
# caller, just paid once per worker instead of once per process.
# ---------------------------------------------------------------------------
_thread_local = threading.local()


def get_ocr_reader(lang: str = "en") -> easyocr.Reader:
    """Return this thread's EasyOCR Reader, initialising it on first use."""
    # Map supported languages to EasyOCR codes.
    # For Japanese, we need both 'en' and 'ja' to handle mixed text.
    langs = ["en"]
    if lang in ("ja", "jp"):
        langs.append("ja")

    cache_key = "_".join(langs)

    readers = getattr(_thread_local, "readers", None)
    if readers is None:
        readers = {}
        _thread_local.readers = readers
    if cache_key not in readers:
        readers[cache_key] = easyocr.Reader(langs, gpu=False, verbose=False)
    return readers[cache_key]


class OCRReader:

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
            link_threshold=0.4,
        )
