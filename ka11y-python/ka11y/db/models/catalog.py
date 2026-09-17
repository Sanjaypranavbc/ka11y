"""
ka11y/db/models/catalog.py
==========================
Static WCAG rule catalogue. Seeded from ``i18n/rules.yml`` (English, the
canonical language) by ``ka11y.db.seed``. Referenced by ``audit_fails`` so the
same rule row serves thousands of fails. No translation table by design.

``rule_code`` is the success-criterion id ("1.4.3") for the catalogue rows,
matching how every finding in ka11y is keyed (``wcag_sc``). Engine-specific
codes (an axe rule id such as "color-contrast") can be added later as extra
rows that point at the same ``success_criterion``.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import Boolean, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ka11y.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class WcagRule(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "wcag_rules"
    __table_args__ = (Index("ix_wcag_rules_success_criterion", "success_criterion"),)

    rule_code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    wcag_version: Mapped[str] = mapped_column(String(20), nullable=False)
    success_criterion: Mapped[str] = mapped_column(String(20), nullable=False)
    level: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    recommendation: Mapped[Optional[str]] = mapped_column(Text)
    understanding_url: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
