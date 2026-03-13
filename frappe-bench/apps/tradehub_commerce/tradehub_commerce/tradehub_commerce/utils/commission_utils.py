# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

"""
Commission Utility Functions

Provides helper functions for the global commission toggle mechanism.
These utilities allow checking whether commission is enabled platform-wide,
returning zero-commission results when disabled, and invalidating the
commission cache when settings change.
"""

import frappe
from frappe import _
from frappe.utils import flt


# Cache TTL in seconds (5 minutes)
COMMISSION_CACHE_TTL = 300


def is_commission_enabled() -> bool:
    """Check whether commission calculation is globally enabled.

    Reads from cache first; on cache miss, queries the
    'TR TradeHub Settings' Single DocType and populates the cache
    with a TTL of 300 seconds.

    Returns:
        True if commission is enabled, False otherwise.
    """
    cached = frappe.cache().get_value("commission_enabled")

    if cached is not None:
        return bool(int(cached))

    # Cache miss — query DB
    enabled = frappe.db.get_single_value("TR TradeHub Settings", "commission_enabled")
    enabled = bool(int(enabled)) if enabled else False

    # Populate cache with TTL
    frappe.cache().set_value(
        "commission_enabled",
        int(enabled),
        expires_in_sec=COMMISSION_CACHE_TTL,
    )

    return enabled


def get_zero_commission_result(order_value: float = 0) -> dict:
    """Return a zero-commission result dict for when commission is globally disabled.

    Used as a bypass response so callers receive a consistent structure
    without performing any commission calculation.

    Args:
        order_value: The order value to pass through as seller_amount.

    Returns:
        Dict with commission_amount=0, effective_rate=0,
        seller_amount=order_value, bypassed=True, and bypass_reason.
    """
    return {
        "commission_amount": 0,
        "effective_rate": 0,
        "seller_amount": flt(order_value),
        "bypassed": True,
        "bypass_reason": _("Commission globally disabled"),
    }


def invalidate_commission_cache() -> None:
    """Invalidate the cached commission_enabled value.

    Should be called whenever the 'commission_enabled' field
    in 'TR TradeHub Settings' is updated, so subsequent calls
    to is_commission_enabled() re-read from the database.
    """
    frappe.cache().delete_value("commission_enabled")
