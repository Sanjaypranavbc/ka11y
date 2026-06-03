import os
import httpx
from fastapi import APIRouter
from a11y.api.v1 import combined, pipeline, crawl, rule_evaluator, assets
from a11y.api.v1.rules import router as rules_router

router = APIRouter(prefix="/api/v1")
router.include_router(crawl.router)
# router.include_router(forms.router)
router.include_router(pipeline.router)
router.include_router(combined.router)
router.include_router(assets.router)
router.include_router(rules_router)
router.include_router(rule_evaluator.router, prefix="/test")


@router.get("/health", tags=["health"])
async def health():
    """Python service health check."""
    return {"status": "ok", "service": "a11y-python"}


@router.get("/system/health", tags=["health"])
async def system_health():
    """Full system health check including Node connectivity."""
    node_base_url = os.getenv("NODE_BASE_URL", "http://localhost:3000")
    node_health_url = f"{node_base_url.rstrip('/')}/api/v1/health"

    node_status = "unknown"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(node_health_url)
            if resp.status_code == 200:
                node_status = "ok"
            else:
                node_status = f"error: {resp.status_code}"
    except Exception as e:
        node_status = f"unreachable: {e}"

    return {
        "python": "ok",
        "node": node_status,
        "node_base_url": node_base_url,
    }
