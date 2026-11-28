# ruff: noqa: E501
"""BOM extraction and sourcing plans. The offers are synthetic parser/maths fixtures with round numbers, so the
expected totals are derived by hand; they are not real prices and never shown to users."""

from __future__ import annotations

import pytest
from via_opt.bom import Offer, PriceBreak, extract_bom, plan

from tests.engineering.synthetic import Board
from via_pcb import parse_pcb


def design(board: Board):
    return parse_pcb(board.bytes(), filename="s.kicad_pcb")


def offer(
    spn, mpn="RC0603FR-0710KL", stock=1000, lead=None, breaks=((1, 0.10),), min_order=1, multiple=1, currency="USD"
):
    return Offer(supplier="mouser", supplier_part_number=spn, mpn=mpn, stock=stock, lead_time_days=lead, currency=currency,
                 price_breaks=[PriceBreak(quantity=q, unit_price=p) for q, p in breaks], min_order=min_order, multiple=multiple)  # fmt: skip


def line(mpn="RC0603FR-0710KL", per_board=3, key=None):
    from via_opt.bom import BomLine

    return BomLine(
        key=key or f"mpn:{mpn.lower()}", references=["R1", "R2", "R3"][:per_board], per_board=per_board, mpn=mpn
    )


def test_extract_bom_groups_by_part_and_skips_do_not_fit():
    b = Board()
    for ref, x in (("R1", 5), ("R2", 10)):
        b.footprint(ref, x, 5, [{"net": "A"}])
    d = design(b)
    for c in d.components:
        c.value, c.properties = "10k", {"MPN": "RC0603FR-0710KL", "Manufacturer": "Yageo"}
    d.components[1].attributes = ["smd", "dnp"]
    extra = d.components[0].model_copy(deep=True)
    extra.reference = "R9"
    d.components.append(extra)
    bom = extract_bom(d)
    assert len(bom) == 1 and bom[0].per_board == 2 and bom[0].references == ["R1", "R9"]
    assert bom[0].mpn == "RC0603FR-0710KL" and bom[0].manufacturer == "Yageo"


def test_a_part_without_an_mpn_is_grouped_by_value_and_footprint_and_cannot_be_priced():
    d = design(Board().footprint("C1", 5, 5, [{"net": "A"}]).footprint("C2", 10, 5, [{"net": "A"}]))
    for c in d.components:
        c.value = "100n"
    (ln,) = extract_bom(d)
    assert ln.mpn is None and ln.per_board == 2 and ln.key.startswith("part:100n|")


def test_the_three_strategies_pick_different_listings_by_hand_derived_totals():
    # 3 per board x 25 boards = 75 parts needed.
    offers = {
        "mpn:rc0603fr-0710kl": [
            offer("CUT", stock=1000, breaks=((1, 0.10),)),  # 75 x 0.10 = 7.50, in stock
            offer("REEL-A", stock=0, lead=7, breaks=((1, 0.08),)),  # 75 x 0.08 = 6.00, 7 days
            offer("REEL-B", stock=0, lead=56, breaks=((1, 0.05),)),  # 75 x 0.05 = 3.75, 56 days
        ]
    }
    p = plan([line()], offers, 25)
    pick = {name: p["strategies"][name]["lines"][0] for name in ("cheapest", "fastest", "balanced")}
    assert (pick["cheapest"]["supplier_part_number"], pick["cheapest"]["total"]) == ("REEL-B", 3.75)
    assert (pick["fastest"]["supplier_part_number"], pick["fastest"]["total"], pick["fastest"]["in_stock"]) == (
        "CUT",
        7.5,
        True,
    )
    # balanced: costs normalised over 3.75..7.50 -> CUT 1.0, A 0.6, B 0.0; lead t = 0, 7/28, 1 -> scores 0.5, 0.425, 0.5
    assert (pick["balanced"]["supplier_part_number"], pick["balanced"]["total"]) == ("REEL-A", 6.0)
    assert p["status"] == "priced" and p["lines_priced"] == 1 and p["currency"] == "USD"
    assert p["strategies"]["cheapest"]["total"] == 3.75


def test_buying_up_to_a_price_break_is_chosen_when_it_costs_less_in_total():
    o = offer("S", stock=1000, breaks=((1, 0.10), (10, 0.08), (100, 0.05)))
    p = plan([line()], {"mpn:rc0603fr-0710kl": [o]}, 25)  # need 75: 75 x 0.08 = 6.00 vs 100 x 0.05 = 5.00
    row = p["strategies"]["cheapest"]["lines"][0]
    assert (row["order_qty"], row["overbuy"], row["unit_price"], row["total"]) == (100, 25, 0.05, 5.0)


def test_minimum_order_and_multiples_are_respected():
    o = offer("S", breaks=((1, 0.10),), min_order=50, multiple=25)
    row = plan([line(per_board=1)], {"mpn:rc0603fr-0710kl": [o]}, 10)["strategies"]["cheapest"]["lines"][0]
    assert row["order_qty"] == 50 and row["total"] == 5.0  # need 10 -> minimum 50
    row = plan([line(per_board=1)], {"mpn:rc0603fr-0710kl": [o]}, 60)["strategies"]["cheapest"]["lines"][0]
    assert row["order_qty"] == 75 and row["total"] == 7.5  # need 60 -> next multiple of 25


def test_lines_that_cant_be_priced_are_listed_with_a_reason_and_left_out_of_the_total():
    lines = [
        line(),
        line("OTHER-PART", key="mpn:other-part"),
        line("NOPRICE", key="mpn:noprice"),
        line("NOMPN", key="part:x|y"),
    ]
    offers = {
        "mpn:rc0603fr-0710kl": [offer("A", breaks=((1, 0.10),))],
        # similar name, different MPN: never treated as the same part
        "mpn:other-part": [offer("SIMILAR", mpn="OTHER-PART-X", breaks=((1, 0.01),))],
        "mpn:noprice": [offer("NP", mpn="NOPRICE", breaks=())],  # the listing states no price
    }
    p = plan(lines, offers, 10, unlooked={"part:x|y": "No manufacturer part number in the design"})
    assert p["status"] == "partial" and p["lines_priced"] == 1 and p["lines"] == 4
    reasons = {u["key"]: u["reason"] for u in p["unpriced"]}
    assert "exact part number" in reasons["mpn:other-part"] and "no usable price" in reasons["mpn:noprice"]
    assert reasons["part:x|y"].startswith("No manufacturer part number")
    assert p["strategies"]["cheapest"]["total"] == 3.0  # only the priced line: 30 x 0.10
    assert any("1 of 4" in n or "of 4 BOM lines" in n for n in p["notes"])


def test_a_first_price_break_above_the_quantity_needed_is_a_buy_up_option_not_a_price_for_less():
    o = offer("S", breaks=((1000, 0.01),))
    row = plan([line(per_board=1)], {"mpn:rc0603fr-0710kl": [o]}, 30)["strategies"]["cheapest"]["lines"][0]
    assert (row["order_qty"], row["overbuy"], row["total"]) == (
        1000,
        970,
        10.0,
    )  # 30 can't be bought at any listed price


def test_nothing_priced_gives_no_totals():
    p = plan([line()], {}, 5)
    assert p["status"] == "none" and p["strategies"] == {} and p["lines_priced"] == 0


def test_unknown_stock_is_never_assumed_in_stock():
    o = offer("S", stock=None, lead=None, breaks=((1, 0.10),))
    row = plan([line()], {"mpn:rc0603fr-0710kl": [o]}, 1)["strategies"]["fastest"]["lines"][0]
    assert row["in_stock"] is None and row["lead_time_days"] is None


def test_offers_in_another_currency_are_not_mixed_into_the_totals():
    offers = {
        "mpn:rc0603fr-0710kl": [offer("USD1", breaks=((1, 0.10),)), offer("EUR1", breaks=((1, 0.01),), currency="EUR")]
    }
    p = plan([line()], offers, 10)
    assert p["currency"] == "USD" and p["strategies"]["cheapest"]["lines"][0]["supplier_part_number"] == "USD1"
    assert p["strategies"]["cheapest"]["total"] == pytest.approx(3.0)
