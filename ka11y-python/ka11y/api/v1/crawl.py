#crawl
import traceback
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl

from ka11y.crawler.crawler import AsyncImageCrawler
from ka11y.config.logger import setup_logger

router = APIRouter(prefix="/crawl", tags=["crawl"])
logger = setup_logger(name="KAC", tag="crawl")


class CrawlRequest(BaseModel):
    url: HttpUrl = "https://www.bluecaffeine.com"
    max_depth: int = 0


class CrawlResponse(BaseModel):
    status: str
    output_dir: str
    url: str
    max_depth: int


@router.post("/", response_model=CrawlResponse)
async def run_crawler(payload: CrawlRequest):
    url = str(payload.url)
    max_depth = payload.max_depth

    logger.info("Starting crawler step")
    logger.info(f"URL: {url}")
    logger.info(f"Max depth: {max_depth}")

    try:
        crawler = AsyncImageCrawler(base_url=url, max_depth=max_depth)
        await crawler.crawl_page()
        crawler.save_results()
        logger.info("Crawler step completed successfully")

        return CrawlResponse(
            status="success",
            output_dir=str(crawler.output_dir),
            url=url,
            max_depth=max_depth
        )

    except Exception as e:
        logger.error(f"Crawler failed: {e}")
        logger.error(traceback.format_exc())  # 👈 add this
        raise HTTPException(status_code=500, detail=str(e))