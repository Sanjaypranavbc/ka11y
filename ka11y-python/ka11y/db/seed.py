"""
ka11y/db/seed.py
================
Seed data for the production DB. Idempotent: safe to run on every startup.

``seed_wcag_rules`` loads the canonical English catalogue from
``i18n/rules.yml`` (via the same loader the rules API uses) and upserts one
``wcag_rules`` row per success criterion. Re-running updates name/description/
recommendation/level in place and never deletes rows, so an ``audit_fails``
FK can never dangle.

CLI::

    DATABASE_URL=... python -m ka11y.db.seed
"""

from __future__ import annotations

import asyncio
from typing import Dict, List

from sqlalchemy import select

from ka11y.config.logger import setup_logger
from ka11y.db.engine import session_scope
from ka11y.db.models import WcagRule

logger = setup_logger(name="KAC", tag="db.seed")

WCAG_VERSION = "2.2"
# Success criteria that WCAG 2.2 dropped. Kept in the catalogue (old audits
# may reference them) but flagged inactive.
_REMOVED_IN_22 = {"4.1.1"}
_UNDERSTANDING_BASE = "https://www.w3.org/WAI/WCAG22/Understanding/"


def _slugify(name: str) -> str:
    """'Non-text Content' → 'non-text-content' (W3C Understanding slugs)."""
    import re

    s = name.lower()
    s = s.replace("&", "and")
    s = re.sub(r"[()]", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def catalogue_rows() -> List[Dict[str, object]]:
    """The rows to seed, derived from i18n/rules.yml (English)."""
    from ka11y.i18n.loader import load_rules

    rows: List[Dict[str, object]] = []
    for sc, entry in load_rules("en").items():
        if not sc or not sc[0].isdigit():
            continue  # '_generic' and other non-SC entries
        rows.append(
            {
                "rule_code": sc,
                "wcag_version": WCAG_VERSION,
                "success_criterion": sc,
                "level": (entry.level or "A").upper(),
                "name": entry.name or sc,
                "description": entry.description or None,
                "recommendation": entry.suggested_fix or None,
                "understanding_url": _UNDERSTANDING_BASE + _slugify(entry.name or sc) + ".html"
                if entry.name
                else None,
                "is_active": sc not in _REMOVED_IN_22,
            }
        )
    return rows


async def seed_wcag_rules() -> int:
    """Upsert the catalogue. Returns the number of rows inserted."""
    rows = catalogue_rows()
    inserted = 0
    async with session_scope() as session:
        existing = {
            r.rule_code: r
            for r in (await session.execute(select(WcagRule))).scalars().all()
        }
        for row in rows:
            cur = existing.get(str(row["rule_code"]))
            if cur is None:
                session.add(WcagRule(**row))
                inserted += 1
            else:
                for k, v in row.items():
                    if getattr(cur, k) != v:
                        setattr(cur, k, v)
    logger.info("[db.seed] wcag_rules: %d catalogue rows, %d inserted", len(rows), inserted)
    return inserted


async def seed_all() -> None:
    await seed_wcag_rules()


if __name__ == "__main__":
    asyncio.run(seed_all())
