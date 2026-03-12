# Copyright (c) 2026, Trade Hub and contributors
# For license information, please see license.txt

"""
Buy Box Disqualification Rules for Trade Hub B2B Marketplace.

This module implements 11 disqualification rules that are checked before
scoring a Buy Box Entry. Disqualified entries are excluded from winner
determination and marked with is_disqualified=1 and a reason.

Disqualification Rules:
    1.  Seller verification_status ≠ "Verified"
    2.  Seller status ≠ "Active"
    3.  Product status ≠ "Active"
    4.  Stock available ≤ 0
    5.  Offer price ≤ 0
    6.  Delivery days ≤ 0
    7.  Buy Box Entry status ≠ "Active"
    8.  Seller suspended or banned
    9.  Seller on_time_delivery_rate < threshold (from Settings)
    10. Seller return_rate > threshold (from Settings)
    11. Seller average_rating < threshold (from Settings)
"""

import frappe
from frappe import _
from frappe.utils import flt, cint


# Default thresholds for metric-based disqualification rules.
# These apply when Buy Box Settings does not specify explicit thresholds.
DEFAULT_MIN_ON_TIME_DELIVERY_RATE = 70.0  # Percentage
DEFAULT_MAX_RETURN_RATE = 20.0  # Percentage
DEFAULT_MIN_AVERAGE_RATING = 2.0  # Out of 5.0


def check_disqualification(entry):
    """
    Check all 11 disqualification rules for a Buy Box Entry.

    Rules are evaluated in order. The first matching rule causes
    disqualification with the corresponding reason. Metric-based rules
    (9-11) only apply if the seller has sufficient order history, as
    configured by min_orders_for_metrics in Buy Box Settings.

    Args:
        entry: Buy Box Entry document or dict-like object with fields:
            - status, offer_price, delivery_days, stock_available
            - seller, seller_tier, seller_average_rating, seller_total_reviews
            - seller_on_time_delivery_rate, seller_refund_rate
            - seller_verification_status, sku_product

    Returns:
        tuple: (is_disqualified, reason)
            - is_disqualified (bool): True if the entry is disqualified
            - reason (str or None): Human-readable disqualification reason
    """
    # Rule 1: Seller verification_status ≠ "Verified"
    result = _check_seller_verification(entry)
    if result:
        return result

    # Rule 2: Seller status ≠ "Active"
    result = _check_seller_status(entry)
    if result:
        return result

    # Rule 3: Product status ≠ "Active"
    result = _check_product_status(entry)
    if result:
        return result

    # Rule 4: Stock available ≤ 0
    result = _check_stock(entry)
    if result:
        return result

    # Rule 5: Offer price ≤ 0
    result = _check_price(entry)
    if result:
        return result

    # Rule 6: Delivery days ≤ 0
    result = _check_delivery(entry)
    if result:
        return result

    # Rule 7: Buy Box Entry status ≠ "Active"
    result = _check_entry_status(entry)
    if result:
        return result

    # Rule 8: Seller suspended or banned
    result = _check_seller_suspended_or_banned(entry)
    if result:
        return result

    # Rules 9–11: Metric-based rules (only if sufficient order history)
    result = _check_metric_thresholds(entry)
    if result:
        return result

    # No disqualification
    return (False, None)


# =============================================================================
# INDIVIDUAL RULE CHECKS
# =============================================================================


def _check_seller_verification(entry):
    """
    Rule 1: Seller verification_status ≠ "Verified".

    Checks the denormalized verification_status field on the Buy Box Entry,
    falling back to querying the Seller Profile directly if not available.
    """
    verification_status = getattr(entry, "seller_verification_status", None)

    if not verification_status:
        seller = getattr(entry, "seller", None)
        if seller:
            verification_status = frappe.db.get_value(
                "Seller Profile", seller, "verification_status"
            )

    if verification_status and verification_status != "Verified":
        return (True, _("Seller is not verified (status: {0})").format(verification_status))

    return None


def _check_seller_status(entry):
    """
    Rule 2: Seller status ≠ "Active".

    Checks the seller's status from the Seller Profile.
    """
    seller = getattr(entry, "seller", None)
    if not seller:
        return (True, _("No seller linked to Buy Box entry"))

    seller_status = frappe.db.get_value("Seller Profile", seller, "status")

    if seller_status and seller_status != "Active":
        return (True, _("Seller is not active (status: {0})").format(seller_status))

    return None


def _check_product_status(entry):
    """
    Rule 3: Product status ≠ "Active".

    Checks the product's status. Uses denormalized product_status field
    if available, otherwise queries SKU Product directly.
    """
    product_status = getattr(entry, "product_status", None)

    if not product_status:
        sku_product = getattr(entry, "sku_product", None)
        if sku_product:
            product_status = frappe.db.get_value(
                "SKU Product", sku_product, "status"
            )

    if product_status and product_status != "Active":
        return (True, _("Product is not active (status: {0})").format(product_status))

    return None


def _check_stock(entry):
    """Rule 4: Stock available ≤ 0."""
    if flt(getattr(entry, "stock_available", 0)) <= 0:
        return (True, _("Stock is not available"))

    return None


def _check_price(entry):
    """Rule 5: Offer price ≤ 0."""
    if flt(getattr(entry, "offer_price", 0)) <= 0:
        return (True, _("Offer price must be greater than zero"))

    return None


def _check_delivery(entry):
    """Rule 6: Delivery days ≤ 0."""
    if cint(getattr(entry, "delivery_days", 0)) <= 0:
        return (True, _("Delivery days must be greater than zero"))

    return None


def _check_entry_status(entry):
    """Rule 7: Buy Box Entry status ≠ "Active"."""
    entry_status = getattr(entry, "status", None)

    if entry_status and entry_status != "Active":
        return (True, _("Buy Box entry is not active (status: {0})").format(entry_status))

    return None


def _check_seller_suspended_or_banned(entry):
    """
    Rule 8: Seller suspended or banned.

    Checks if the seller's status is "Suspended" or "Blocked" in the
    Seller Profile. This is distinct from Rule 2 which checks for non-Active
    status generally; this rule specifically flags suspended/banned sellers
    with a more severe disqualification reason.
    """
    seller = getattr(entry, "seller", None)
    if not seller:
        return None

    seller_status = frappe.db.get_value("Seller Profile", seller, "status")

    if seller_status in ("Suspended", "Blocked"):
        return (True, _("Seller account is {0}").format(seller_status.lower()))

    return None


def _check_metric_thresholds(entry):
    """
    Rules 9–11: Metric-based disqualification thresholds.

    These rules only apply to sellers with sufficient order history
    (determined by min_orders_for_metrics in Buy Box Settings).

    Rule 9:  on_time_delivery_rate < minimum threshold
    Rule 10: return_rate > maximum threshold
    Rule 11: average_rating < minimum threshold

    Thresholds are read from Buy Box Settings where available,
    with sensible defaults as fallback.
    """
    settings = _get_settings_cached()
    min_orders = cint(settings.min_orders_for_metrics) if settings else 5

    # Check if seller has enough order history for metric evaluation
    total_reviews = cint(getattr(entry, "seller_total_reviews", 0) or 0)
    if total_reviews < min_orders:
        return None  # Skip metric checks for new sellers

    # Rule 9: on_time_delivery_rate below threshold
    on_time_rate = flt(getattr(entry, "seller_on_time_delivery_rate", 0) or 0)
    min_on_time = _get_threshold(settings, "min_on_time_delivery_rate", DEFAULT_MIN_ON_TIME_DELIVERY_RATE)

    if on_time_rate > 0 and on_time_rate < min_on_time:
        return (
            True,
            _("On-time delivery rate ({0}%) is below minimum threshold ({1}%)").format(
                on_time_rate, min_on_time
            )
        )

    # Rule 10: return_rate above threshold
    return_rate = flt(getattr(entry, "seller_refund_rate", 0) or 0)
    max_return = _get_threshold(settings, "max_return_rate", DEFAULT_MAX_RETURN_RATE)

    if return_rate > max_return:
        return (
            True,
            _("Return rate ({0}%) exceeds maximum threshold ({1}%)").format(
                return_rate, max_return
            )
        )

    # Rule 11: average_rating below threshold
    avg_rating = flt(getattr(entry, "seller_average_rating", 0) or 0)
    min_rating = _get_threshold(settings, "min_average_rating", DEFAULT_MIN_AVERAGE_RATING)

    if avg_rating > 0 and avg_rating < min_rating:
        return (
            True,
            _("Seller average rating ({0}) is below minimum threshold ({1})").format(
                avg_rating, min_rating
            )
        )

    return None


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================


def _get_settings_cached():
    """
    Get Buy Box Settings with request-level caching.

    Returns:
        Document or None: Buy Box Settings document
    """
    try:
        return frappe.get_single("Buy Box Settings")
    except Exception:
        return None


def _get_threshold(settings, field_name, default_value):
    """
    Read a threshold value from Buy Box Settings with fallback to default.

    Supports future extension of Buy Box Settings with threshold fields
    without requiring code changes.

    Args:
        settings: Buy Box Settings document (may be None)
        field_name: The field name to look up on settings
        default_value: Default value if field doesn't exist or settings is None

    Returns:
        float: The threshold value
    """
    if settings and hasattr(settings, field_name):
        value = flt(getattr(settings, field_name, 0))
        if value > 0:
            return value

    return flt(default_value)
