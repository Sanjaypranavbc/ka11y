import os
import httpx
from fastapi import APIRouter, Depends
from ka11y.api.v1 import audits, combined, pipeline, crawl, rule_evaluator, assets
from ka11y.api.v1.rules import router as rules_router
from ka11y.auth import require_user
from ka11y.auth.router import router as auth_router

router = APIRouter(prefix="/api/v1")

# Public: sign-in flow and health checks (Docker healthchecks hit /health).
router.include_router(auth_router)

# Everything that runs a browser, reads a report or serves an asset needs a
# signed-in user. With KA11Y_AUTH_DISABLED=1 (tests, local dev) the dependency
# resolves to an anonymous caller instead of a 401.
_protected = [Depends(require_user)]
router.include_router(crawl.router, dependencies=_protected)
router.include_router(pipeline.router, dependencies=_protected)
router.include_router(combined.router, dependencies=_protected)
router.include_router(assets.router, dependencies=_protected)
router.include_router(audits.router)  # declares require_user itself (needs the user object)
router.include_router(rules_router, dependencies=_protected)
router.include_router(rule_evaluator.router, prefix="/test", dependencies=_protected)


@router.get("/health", tags=["health"])
async def health():
    """Python service health check."""
    return {"status": "ok", "service": "ka11y-python"}


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
