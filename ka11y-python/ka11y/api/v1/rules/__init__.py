from fastapi import APIRouter
from .metadata import router as metadata_router
from .run_router import router as run_router

router = APIRouter(prefix="/rules")

# Include the metadata routes (e.g. /rules/wcag)
router.include_router(metadata_router, tags=["rules-metadata"])

# Include the individual run routes (e.g. /rules/1.1.1/run)
router.include_router(run_router)
