"""Delivery service layer — module 14.

Full spec: docs/modules/14-delivery.md

Implements: Monday digest composition/rendering/SMTP delivery, and CSV
export of APPROVED records. Always sends even with an empty new-recommended
section (a silent skip is indistinguishable from a failure — see §11). Not
implemented yet — stubs only.
"""
from __future__ import annotations

from app.delivery.schema import DigestContent, DigestSendRecord


def compose_monday_digest() -> DigestContent:
    """Windows by the last successful send's sent_at (default: 7 days back
    if none). new_recommended = created since last send. closing_within_21
    = any queued/approved record within the window regardless of
    created_at. See §7.1, §8.
    """
    raise NotImplementedError("See docs/modules/14-delivery.md §7.1, §8")


def send_monday_digest() -> DigestSendRecord:
    """Renders and sends via SMTP (module 16 secrets); logs every attempt,
    success or failure, to digest_sends for monitoring (module 16). See
    §7.2, §7.3, §7.5, §8.
    """
    raise NotImplementedError("See docs/modules/14-delivery.md §7.2, §7.3, §7.5, §8")


def export_approved_csv() -> str:
    """CSV export of APPROVED records; stream/paginate for large historical
    exports. See §7.4.
    """
    raise NotImplementedError("See docs/modules/14-delivery.md §7.4")
