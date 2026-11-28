# ruff: noqa: E501
"""Mouser client parsing. The responses are synthetic, built to Mouser's documented shape with round numbers; they
check parsing and error handling, not real prices."""

from __future__ import annotations

import pytest

from via_api.suppliers.mouser import MouserClient, SupplierError, parse_lead_days, parse_offers, parse_price


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("$0.10", 0.10), ("0,10 €", 0.10), ("1,234.50", 1234.5), ("1.234,50 €", 1234.5), ("€1,234", 1234.0),
        ("£12", 12.0), ("US$0.0125", 0.0125), (0.25, 0.25), ("", None), ("n/a", None), (None, None), ("--", None),
    ],
)  # fmt: skip
def test_parse_price(text, value):
    assert parse_price(text) == value


@pytest.mark.parametrize(
    ("text", "days"), [("35 Days", 35), ("12 Weeks", 84), ("1 week", 7), ("", None), ("Contact", None), (None, None)]
)
def test_parse_lead_days(text, days):
    assert parse_lead_days(text) == days


def part(**kw):
    base = {
        "Manufacturer": "ACME", "ManufacturerPartNumber": "ABC-123", "MouserPartNumber": "123-ABC-123", "Min": "1", "Mult": "1",
        "AvailabilityInStock": "1,200", "Availability": "1,200 In Stock", "LeadTime": "35 Days",
        "ProductDetailUrl": "https://www.mouser.com/ProductDetail/ACME/ABC-123",
        "PriceBreaks": [{"Quantity": 1, "Price": "$0.10", "Currency": "USD"}, {"Quantity": 100, "Price": "$0.05", "Currency": "USD"}],
    }  # fmt: skip
    return {**base, **kw}


def test_parse_offers_reads_stock_breaks_lead_time_and_limits():
    (o,) = parse_offers({"Errors": [], "SearchResults": {"NumberOfResult": 1, "Parts": [part(Min="10", Mult="5")]}})
    assert (o.supplier, o.mpn, o.supplier_part_number, o.manufacturer) == ("mouser", "ABC-123", "123-ABC-123", "ACME")
    assert (o.stock, o.lead_time_days, o.min_order, o.multiple, o.currency) == (1200, 35, 10, 5, "USD")
    assert [(b.quantity, b.unit_price) for b in o.price_breaks] == [(1, 0.10), (100, 0.05)]
    assert o.url == "https://www.mouser.com/ProductDetail/ACME/ABC-123"


def test_stock_falls_back_to_the_availability_text_and_unknown_stays_unknown():
    (a,) = parse_offers({"SearchResults": {"Parts": [part(AvailabilityInStock=None, Availability="500 In Stock")]}})
    (b,) = parse_offers({"SearchResults": {"Parts": [part(AvailabilityInStock=None, Availability="On Order")]}})
    assert a.stock == 500 and b.stock is None


def test_unparseable_prices_are_skipped_not_guessed_and_unsafe_urls_are_dropped():
    (o,) = parse_offers(
        {
            "SearchResults": {
                "Parts": [
                    part(
                        PriceBreaks=[
                            {"Quantity": 1, "Price": "Call", "Currency": "USD"},
                            {"Quantity": 10, "Price": "$0.08", "Currency": "USD"},
                        ],
                        ProductDetailUrl="https://evil.example.com/x",
                    )
                ]
            }
        }
    )
    assert [(b.quantity, b.unit_price) for b in o.price_breaks] == [(10, 0.08)] and o.url is None
    assert parse_offers({"SearchResults": {"Parts": [part(ManufacturerPartNumber="")]}}) == []
    assert parse_offers({"SearchResults": {"Parts": None}}) == [] and parse_offers({}) == []


def test_api_errors_become_safe_messages_and_never_echo_the_key():
    with pytest.raises(SupplierError) as bad_key:
        parse_offers(
            {"Errors": [{"Id": 0, "Code": "Invalid", "Message": "Invalid unique identifier. apiKey=SECRET123"}]}
        )
    assert bad_key.value.fatal and "SECRET123" not in str(bad_key.value)
    with pytest.raises(SupplierError) as limit:
        parse_offers({"Errors": [{"Message": "Too many requests"}]})
    assert limit.value.fatal
    with pytest.raises(SupplierError) as other:
        parse_offers({"Errors": [{"Message": "Something odd about SECRET123"}]})
    assert not other.value.fatal and "SECRET123" not in str(other.value)


def test_the_client_sends_the_part_number_spaces_calls_and_hides_the_key():
    calls, sleeps = [], []

    def transport(url, body):
        calls.append((url, body))
        return {"SearchResults": {"Parts": [part()]}}

    client = MouserClient("KEY/with+chars", transport=transport, sleep=sleeps.append)
    client.offers("ABC-123")
    client.offers("DEF-456")
    assert calls[0][1] == {"SearchByPartRequest": {"mouserPartNumber": "ABC-123"}}
    assert calls[0][0].endswith("apiKey=KEY%2Fwith%2Bchars")
    assert len(sleeps) == 1 and 0 < sleeps[0] <= 2.1  # the second call waited; the first didn't
    assert "KEY" not in repr(client)
