from fastapi import APIRouter
from ka11y.api.v1 import crawl, forms, pipeline, combined

router = APIRouter(prefix="/api/v1")
# router.include_router(crawl.router)
# router.include_router(forms.router)
router.include_router(pipeline.router)
router.include_router(combined.router)
