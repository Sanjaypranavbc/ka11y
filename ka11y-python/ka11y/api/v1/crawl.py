import traceback
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl

from ka11y.crawler.crawler import AsyncImageCrawler
from ka11y.text_detector.text_detector import OCRPreprocessing, TextClassification
from ka11y.config.logger import setup_logger

router = APIRouter(prefix="/crawl", tags=["crawl"])
logger = setup_logger(name="KAC", tag="crawl")


class CrawlRequest(BaseModel):
    url: HttpUrl = "https://www.kao.com/global/en/"
    max_depth: int = 0
    run_ocr: bool = True


class CrawlResponse(BaseModel):
    status: str
    output_dir: str
    url: str
    max_depth: int
    ocr_dir: str | None = None


@router.post("/", response_model=CrawlResponse)
async def run_crawler(payload: CrawlRequest):
    url = str(payload.url)
    max_depth = payload.max_depth

    logger.info("Starting crawler step")
    logger.info(f"URL: {url}")
    logger.info(f"Max depth: {max_depth}")

    try:
        # ── STEP 1: Crawl ──
        crawler = AsyncImageCrawler(base_url=url, max_depth=max_depth)
        await crawler.crawl_page()
        crawler.save_results()
        logger.info("Crawler step completed successfully")

        # ── STEP 2: OCR (optional) ──
        ocr_dir = None
        if payload.run_ocr:
            logger.info(f"Running OCR on: {crawler.output_dir}")

            logger.info("\n" + "=" * 60)
            logger.info("STEP 2: TEXT DETECTION & CONTRAST ANALYSIS (EasyOCR)")
            logger.info("=" * 60 + "\n")

            detector = OCRPreprocessing(source_directory=crawler.output_dir)
            detector.scan_directory()

            save = TextClassification(source_directory=crawler.output_dir)
            save.results = detector.results
            save.save_reports()
            logger.info("OCR step completed successfully")

        return CrawlResponse(
            status="success",
            output_dir=str(crawler.output_dir),
            url=url,
            max_depth=max_depth,
            ocr_dir=ocr_dir,
        )

    except Exception as e:
        logger.error(f"Crawler failed: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
