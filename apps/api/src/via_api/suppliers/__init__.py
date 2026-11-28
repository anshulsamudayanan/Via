"""Supplier pricing lookups (Mouser). Only manufacturer part numbers leave VIA, and only with the project owner's
``supplier_lookup`` consent. The key is read from ``MOUSER_API_KEY`` in the environment, never stored or logged."""

from __future__ import annotations

import os

from via_api.suppliers.mouser import MouserClient, SupplierError

__all__ = ["MouserClient", "SupplierError", "get_supplier"]


def get_supplier() -> MouserClient | None:
    """The configured supplier, or None when no key is set."""
    key = os.environ.get("MOUSER_API_KEY", "").strip()
    return MouserClient(key) if key else None
