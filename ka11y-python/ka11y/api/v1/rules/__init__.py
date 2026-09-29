"""
ka11y/api/v1/rules
==================
Read-only WCAG rule catalogue (``GET /rules/wcag``).

The per-rule job launchers that used to live here (``POST /rules/{sc}/run``,
``/rules/{sc}/analyse-url``) were removed on 2026-09-27: they referenced
request flags that no longer existed, so every job they created failed, and
nothing called them. Audit a single criterion with
``POST /combined/python-audit`` + ``success_criteria_id`` instead.
"""

from fastapi import APIRouter

from .metadata import router as metadata_router

router = APIRouter(prefix="/rules")
router.include_router(metadata_router, tags=["rules-metadata"])
