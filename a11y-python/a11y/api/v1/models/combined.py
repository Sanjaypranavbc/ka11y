"""
a11y/api/v1/models/combined.py
=================================
Bug 8 fix: this module was a stale duplicate of a11y/api/v1/combined/models.py
that was missing the newer rendered-layout audit flags added to CombinedRequest
(run_resize_text_audit, run_reflow_audit, run_orientation_audit, etc.).

All definitions are now re-exported from the canonical source of truth so that
any existing import path continues to work without drifting from the real schema.
"""

from a11y.api.v1.combined.models import CombinedRequest, JobStatusResponse

__all__ = ["CombinedRequest", "JobStatusResponse"]
