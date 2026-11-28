"""Mouser Search API client (part-number search), using only the standard library.

One request per part number. The key travels in the query string as Mouser requires, so it is never put in an
error message or log line. Mouser allows about 30 calls a minute, so calls are spaced. The shape of the response
(``SearchResults.Parts[]`` with ``PriceBreaks``, ``AvailabilityInStock``, ``LeadTime``, ``Min``, ``Mult``) follows
Mouser's published API; prices come back as locale-formatted strings and are parsed defensively. A listing that
can't be parsed is skipped, never guessed.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from via_opt.bom import Offer, PriceBreak

API_URL = "https://api.mouser.com/api/v1/search/partnumber"
USER_AGENT = "via-optimize/0.1 (+https://github.com/anshulsamudayanan/Via)"
TIMEOUT_SECONDS = 30
MIN_INTERVAL_SECONDS = 2.1  # Mouser: 30 calls per minute

Transport = Callable[[str, dict[str, Any]], dict[str, Any]]


class SupplierError(Exception):
    """A supplier problem with a message that is safe to show (never contains the key)."""

    def __init__(self, message: str, *, fatal: bool = False) -> None:
        super().__init__(message)
        #: The remaining lookups in this run would fail the same way (bad key, rate limit).
        self.fatal = fatal


def _http_post(url: str, body: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(  # noqa: S310 - fixed https URL
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Accept": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:  # noqa: S310
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise SupplierError("Mouser rejected the API key. Check MOUSER_API_KEY.", fatal=True) from None
        if exc.code == 429:
            raise SupplierError("Mouser's rate limit was reached.", fatal=True) from None
        raise SupplierError(f"Mouser returned an error (HTTP {exc.code}).") from None
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise SupplierError("Couldn't reach Mouser.") from exc


def parse_price(text: object) -> float | None:
    """'$0.10', '0,10 €', '1,234.50', '1.234,50 €' -> float. None when it isn't a clear number."""
    if isinstance(text, int | float) and not isinstance(text, bool):
        return float(text)
    cleaned = re.sub(r"[^\d.,]", "", str(text or ""))
    if not cleaned or not re.search(r"\d", cleaned):
        return None
    if "," in cleaned and "." in cleaned:
        decimal = "," if cleaned.rfind(",") > cleaned.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        cleaned = cleaned.replace(thousands, "").replace(decimal, ".")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+", cleaned) else cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _int(value: object) -> int | None:
    m = re.search(r"\d[\d,]*", str(value or ""))
    return int(m.group().replace(",", "")) if m else None


def parse_lead_days(text: object) -> int | None:
    m = re.search(r"(\d+)\s*(day|week)", str(text or ""), re.I)
    if not m:
        return None
    return int(m.group(1)) * (7 if m.group(2).lower() == "week" else 1)


def _safe_url(url: object) -> str | None:
    parsed = urllib.parse.urlparse(str(url or ""))
    host = (parsed.hostname or "").lower()
    return str(url) if parsed.scheme == "https" and (host == "mouser.com" or host.endswith(".mouser.com")) else None


def parse_offers(response: dict[str, Any]) -> list[Offer]:
    errors = response.get("Errors") or []
    if errors:
        message = " ".join(str(e.get("Message", "")) for e in errors if isinstance(e, dict))
        if re.search(r"invalid unique identifier|api ?key|apikey", message, re.I):
            raise SupplierError("Mouser rejected the API key. Check MOUSER_API_KEY.", fatal=True)
        if re.search(r"too many|rate|limit", message, re.I):
            raise SupplierError("Mouser's rate limit was reached.", fatal=True)
        raise SupplierError("Mouser reported an error for this part number.")
    out: list[Offer] = []
    for part in (response.get("SearchResults") or {}).get("Parts") or []:
        mpn = str(part.get("ManufacturerPartNumber") or "").strip()
        breaks: list[PriceBreak] = []
        currency = None
        for b in part.get("PriceBreaks") or []:
            price, qty = parse_price(b.get("Price")), _int(b.get("Quantity"))
            if price is not None and qty:
                breaks.append(PriceBreak(quantity=qty, unit_price=price))
                currency = currency or (str(b.get("Currency") or "").strip() or None)
        if not mpn:
            continue
        stock = _int(part.get("AvailabilityInStock"))
        if stock is None and re.search(r"in stock", str(part.get("Availability") or ""), re.I):
            stock = _int(part.get("Availability"))
        out.append(
            Offer(
                supplier="mouser", supplier_part_number=str(part.get("MouserPartNumber") or ""), mpn=mpn,
                manufacturer=str(part.get("Manufacturer") or "") or None, stock=stock,
                lead_time_days=parse_lead_days(part.get("LeadTime")), price_breaks=breaks, currency=currency,
                min_order=max(_int(part.get("Min")) or 1, 1), multiple=max(_int(part.get("Mult")) or 1, 1),
                url=_safe_url(part.get("ProductDetailUrl")),
            )
        )  # fmt: skip
    return out


class MouserClient:
    name = "mouser"

    def __init__(
        self, api_key: str, transport: Transport | None = None, sleep: Callable[[float], None] = time.sleep
    ) -> None:
        self._key = api_key
        self._post = transport or _http_post
        self._sleep = sleep
        self._last = 0.0

    def __repr__(self) -> str:  # never show the key
        return "MouserClient()"

    def offers(self, mpn: str) -> list[Offer]:
        """Listings Mouser returns for a manufacturer part number (the caller keeps only exact matches)."""
        wait = MIN_INTERVAL_SECONDS - (time.monotonic() - self._last)
        if self._last and wait > 0:
            self._sleep(wait)
        self._last = time.monotonic()
        url = f"{API_URL}?apiKey={urllib.parse.quote(self._key, safe='')}"
        return parse_offers(self._post(url, {"SearchByPartRequest": {"mouserPartNumber": mpn}}))
