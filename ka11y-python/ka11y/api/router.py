from fastapi import APIRouter
from ka11y.api.v1 import crawl

router = APIRouter(prefix="/api/v1")
router.include_router(crawl.router)
