# ruff: noqa: E501
"""BOM extraction and sourcing plans from real supplier offers.

VIA never invents a price. A line is priced only from an offer returned by a supplier for the *same manufacturer
part number*; everything else is listed as unpriced with the reason. Parts with similar names are never treated as
interchangeable (no substitution is suggested: that needs a parametric compatibility check VIA doesn't have yet).

Three sourcing strategies are computed per line from the offers' price breaks, stock and lead time:

* ``cheapest``: the lowest total for the quantity needed, buying up to a higher price break when that costs less
  in total, whether or not the supplier has the stock yet.
* ``fastest``: what the supplier can ship from stock now (cheapest of those); if nothing is in stock, the
  shortest stated lead time.
* ``balanced``: the lowest equal-weight score of cost and lead time. Cost is normalised across the line's options
  (0 = cheapest, 1 = dearest). Lead time is 0 when in stock, lead_days / 28 (at most 1) otherwise, and 1 when the
  supplier states none.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from via_pcb.models import PCBDesign

VERSION = "1.0.0"
STRATEGIES = ("cheapest", "fastest", "balanced")
#: A lead time of this many days or more counts as the worst for the balanced strategy.
LEAD_SCALE_DAYS = 28
#: Footprint property names that hold a manufacturer part number / manufacturer (compared case-insensitively).
MPN_KEYS = {"mpn", "manufacturer_part_number", "manufacturer part number", "partnumber", "part number", "pn",
            "mfr_pn", "mfr. no", "mfr part number", "mfn"}  # fmt: skip
MFR_KEYS = {"manufacturer", "mfr", "mfr.", "manufacturer_name"}
_EXCLUDED = {"dnp", "exclude_from_bom"}


def part_identity(properties: Mapping[str, str]) -> tuple[str | None, str | None]:
    """(manufacturer, part number) from a component's properties, if present."""
    lower = {k.strip().lower(): v.strip() for k, v in (properties or {}).items() if v and v.strip()}
    mpn = next((lower[k] for k in MPN_KEYS if k in lower), None)
    mfr = next((lower[k] for k in MFR_KEYS if k in lower), None)
    return mfr, mpn


class BomLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key: str
    references: list[str]
    per_board: int
    value: str | None = None
    footprint: str = ""
    manufacturer: str | None = None
    mpn: str | None = Field(default=None, description="Manufacturer part number; only lines with one can be priced")


class PriceBreak(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity: int = Field(ge=1)
    unit_price: float = Field(ge=0)


class Offer(BaseModel):
    """One supplier listing for a manufacturer part number, exactly as the supplier reported it."""

    model_config = ConfigDict(extra="forbid")

    supplier: str
    supplier_part_number: str = ""
    manufacturer: str | None = None
    mpn: str
    stock: int | None = None
    lead_time_days: int | None = None
    price_breaks: list[PriceBreak] = Field(default_factory=list)
    currency: str | None = None
    min_order: int = 1
    multiple: int = 1
    url: str | None = None


def extract_bom(design: PCBDesign) -> list[BomLine]:
    """One line per distinct part (by MPN when present, else value + footprint). Do-not-fit parts are left out."""
    groups: dict[str, BomLine] = {}
    for c in design.components:
        if _EXCLUDED & {a.lower() for a in c.attributes}:
            continue
        mfr, mpn = part_identity(c.properties)
        key = f"mpn:{mpn.lower()}" if mpn else f"part:{(c.value or '').strip().lower()}|{c.footprint.lower()}"
        line = groups.get(key)
        if line is None:
            groups[key] = BomLine(
                key=key,
                references=[c.reference],
                per_board=1,
                value=c.value,
                footprint=c.footprint,
                manufacturer=mfr,
                mpn=mpn,
            )
        else:
            line.references.append(c.reference)
            line.per_board += 1
    for line in groups.values():
        line.references.sort()
    return sorted(groups.values(), key=lambda ln: (ln.references[0] if ln.references else "", ln.key))


def _round_up(q: int, multiple: int) -> int:
    m = max(multiple, 1)
    return -(-q // m) * m


def _price_at(offer: Offer, qty: int) -> float | None:
    """The unit price of the largest price break not above ``qty``; none if ``qty`` is below the first break."""
    price = None
    for b in sorted(offer.price_breaks, key=lambda b: b.quantity):
        if b.quantity <= qty:
            price = b.unit_price
    return price


class _Option(BaseModel):
    offer: Offer
    order_qty: int
    unit_price: float
    total: float
    in_stock: bool | None
    lead_days: int | None


def _options(offer: Offer, needed: int) -> list[_Option]:
    base = _round_up(max(needed, offer.min_order), offer.multiple)
    quantities = {base} | {_round_up(b.quantity, offer.multiple) for b in offer.price_breaks if b.quantity > base}
    out = []
    for q in sorted(quantities):
        unit = _price_at(offer, q)
        if unit is None:
            continue
        in_stock = None if offer.stock is None else offer.stock >= q
        out.append(
            _Option(
                offer=offer,
                order_qty=q,
                unit_price=unit,
                total=round(unit * q, 4),
                in_stock=in_stock,
                lead_days=offer.lead_time_days,
            )
        )
    return out


def _choose(strategy: str, options: list[_Option]) -> _Option:
    def tie(o: _Option) -> tuple[float, int, str]:
        return (o.total, o.order_qty, o.offer.supplier_part_number)

    if strategy == "cheapest":
        return min(options, key=tie)
    if strategy == "fastest":
        stocked = [o for o in options if o.in_stock]
        if stocked:
            return min(stocked, key=tie)
        return min(options, key=lambda o: (o.lead_days is None, o.lead_days or 0, *tie(o)))
    # balanced: equal weights on normalised cost and lead time
    totals = [o.total for o in options]
    lo, hi = min(totals), max(totals)

    def score(o: _Option) -> tuple[float, tuple[float, int, str]]:
        cost = (o.total - lo) / (hi - lo) if hi > lo else 0.0
        if o.in_stock:
            t = 0.0
        elif o.lead_days is None:
            t = 1.0
        else:
            t = min(o.lead_days / LEAD_SCALE_DAYS, 1.0)
        return (0.5 * cost + 0.5 * t, tie(o))

    return min(options, key=score)


def plan(
    lines: list[BomLine],
    offers: Mapping[str, list[Offer]],
    build_quantity: int,
    *,
    unlooked: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Sourcing plans per strategy. ``offers`` is keyed by line key; ``unlooked`` gives a reason per line that wasn't
    looked up (no part number, lookup limit, supplier error). Totals cover priced lines only and say how many."""
    unlooked = unlooked or {}
    unpriced: list[dict[str, Any]] = []
    priced: list[tuple[BomLine, list[_Option]]] = []
    currency: str | None = None
    for line in lines:
        needed = line.per_board * build_quantity
        if line.key in unlooked:
            unpriced.append({"key": line.key, "references": line.references, "reason": unlooked[line.key]})
            continue
        matching = [
            o for o in offers.get(line.key, []) if line.mpn and o.mpn.strip().lower() == line.mpn.strip().lower()
        ]
        options: list[_Option] = []
        for offer in matching:
            if currency is None and offer.currency:
                currency = offer.currency
            if offer.currency == currency or offer.currency is None:
                options += _options(offer, needed)
        if not options:
            reason = (
                "The supplier has no listing with this exact part number."
                if not matching
                else "The listing has no usable price for this quantity."
            )
            unpriced.append({"key": line.key, "references": line.references, "reason": reason})
            continue
        priced.append((line, options))
    strategies: dict[str, Any] = {}
    for name in STRATEGIES:
        rows: list[dict[str, Any]] = []
        for line, options in priced:
            o = _choose(name, options)
            rows.append({
                "key": line.key, "references": line.references, "mpn": line.mpn, "needed": line.per_board * build_quantity,
                "order_qty": o.order_qty, "overbuy": o.order_qty - line.per_board * build_quantity, "unit_price": o.unit_price,
                "total": o.total, "in_stock": o.in_stock, "lead_time_days": o.lead_days,
                "supplier_part_number": o.offer.supplier_part_number, "url": o.offer.url,
            })  # fmt: skip
        strategies[name] = {"total": round(sum(r["total"] for r in rows), 2), "lines": rows}
    complete = bool(lines) and not unpriced
    return {
        "version": VERSION,
        "status": "priced" if complete else ("partial" if priced else "none"),
        "supplier": next((o.offer.supplier for _, opts in priced for o in opts), None),
        "currency": currency,
        "build_quantity": build_quantity,
        "lines": len(lines),
        "lines_priced": len(priced),
        "unpriced": unpriced,
        "strategies": strategies if priced else {},
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "notes": [
            "Prices are the supplier's own listing at the time shown; they change and are not a quote or a commitment.",
            *([] if complete else [f"Totals cover {len(priced)} of {len(lines)} BOM lines; the unpriced lines are listed and not included."]),
            "Only listings with exactly the same manufacturer part number are used. VIA does not suggest substitutes.",
        ],
    }  # fmt: skip
