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
from frappe.utils import date_diff, flt, getdate, nowdate


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


# Banner display threshold in days — shows warning banner when commission
# was re-enabled less than this many days ago.
COMMISSION_REENABLE_WARNING_DAYS = 30


def get_commission_banner_info(seller: str = None) -> dict:
    """Return banner display information based on the commission toggle state.

    Rules:
    - Commission OFF → info banner telling the seller that commission is
      currently disabled.
    - Commission ON and was re-enabled less than 30 days ago → warning
      banner reminding the seller that commission has been recently
      re-enabled.
    - Otherwise → no banner.

    Args:
        seller: Seller Profile name (currently unused but reserved for
                future per-seller overrides).

    Returns:
        Dict with show_banner (bool), banner_type ('info' or 'warning'),
        and message (str).
    """
    commission_enabled = is_commission_enabled()

    if not commission_enabled:
        # Commission is turned OFF — show info banner
        return {
            "show_banner": True,
            "banner_type": "info",
            "message": _(
                "Commission is currently disabled. No commission will be "
                "deducted from your transactions."
            ),
        }

    # Commission is ON — check if it was recently re-enabled
    enabled_since = None
    try:
        enabled_since = frappe.db.get_single_value(
            "TR TradeHub Settings", "commission_enabled_since"
        )
    except Exception:
        pass

    if enabled_since:
        days_since = date_diff(nowdate(), getdate(enabled_since))
        if days_since < COMMISSION_REENABLE_WARNING_DAYS:
            return {
                "show_banner": True,
                "banner_type": "warning",
                "message": _(
                    "Commission was re-enabled {0} days ago. Standard "
                    "commission rates now apply to all transactions."
                ).format(days_since),
            }

    # Commission is ON and stable — no banner needed
    return {
        "show_banner": False,
        "banner_type": None,
        "message": "",
    }
