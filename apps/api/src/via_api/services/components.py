"""Component records: stored part information and how design components match it.

VIA never fills in component specifications itself. Records are created by users (or later by
importers that cite their source); every spec carries its source and whether it was verified.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session
from via_opt.bom import part_identity

from via_api.models import ComponentRecord, PCBComponent


def matches(
    db: Session, project_id: uuid.UUID, components: list[PCBComponent]
) -> list[tuple[PCBComponent, str | None, str | None, ComponentRecord | None]]:
    records = db.scalars(select(ComponentRecord).where(ComponentRecord.project_id == project_id)).all()
    by_pn: dict[str, list[ComponentRecord]] = {}
    for r in records:
        by_pn.setdefault(r.part_number.strip().lower(), []).append(r)
    out = []
    for c in components:
        mfr, mpn = part_identity(c.properties)
        record = None
        if mpn:
            candidates = by_pn.get(mpn.lower(), [])
            if mfr:
                candidates = [r for r in candidates if r.manufacturer.strip().lower() == mfr.lower()] or candidates
            record = candidates[0] if candidates else None
        out.append((c, mfr, mpn, record))
    return out
