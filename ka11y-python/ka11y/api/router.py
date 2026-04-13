from fastapi import APIRouter
from ka11y.api.v1 import combined, pipeline, crawl
from ka11y.api.v1.rules import router as rules_router

router = APIRouter(prefix="/api/v1")
router.include_router(crawl.router)
# router.include_router(forms.router)
router.include_router(pipeline.router)
router.include_router(combined.router)
router.include_router(rules_router)


@router.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}
