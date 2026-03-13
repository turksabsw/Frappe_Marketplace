# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

"""
RFQ View Limits

Subscription-based RFQ view limit enforcement, logging, and statistics.
Provides functions to check view quotas, log views with deduplication,
and retrieve monthly usage statistics tied to seller subscriptions.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime, getdate, nowdate
from typing import Dict, Any, List, Optional


# Cache TTL in seconds (1 hour)
CACHE_TTL = 3600


def _response(success: bool, data: Any = None, message: str = None, errors: List = None) -> Dict:
    """Standard API response format."""
    return {
        "success": success,
        "data": data,
        "message": message,
        "errors": errors or []
    }


def _get_current_month_key() -> str:
    """Get current year-month string for cache keys and queries."""
    today = getdate(nowdate())
    return f"{today.year}-{today.month:02d}"


def _get_month_start_end(month_key: str = None):
    """Get the first and last datetime of a given month.

    Args:
        month_key: Year-month string (e.g. '2026-03'). Defaults to current month.

    Returns:
        Tuple of (start_datetime, end_datetime) as strings.
    """
    if not month_key:
        month_key = _get_current_month_key()

    year, month = month_key.split("-")
    year, month = int(year), int(month)

    import calendar
    last_day = calendar.monthrange(year, month)[1]

    start = f"{year}-{month:02d}-01 00:00:00"
    end = f"{year}-{month:02d}-{last_day} 23:59:59"
    return start, end


def _get_cache_key(seller_profile: str) -> str:
    """Build cache key for RFQ view count.

    Args:
        seller_profile: Seller Profile name.

    Returns:
        Cache key string in format 'rfq_view_count:{seller}:{month}'.
    """
    month_key = _get_current_month_key()
    return f"rfq_view_count:{seller_profile}:{month_key}"


def _get_active_subscription(seller_profile: str) -> Optional[str]:
    """Get the active subscription for a seller.

    Args:
        seller_profile: Seller Profile name.

    Returns:
        Subscription name or None if no active subscription.
    """
    return frappe.db.get_value(
        "Subscription",
        {
            "seller_profile": seller_profile,
            "status": ["in", ["Active", "Trial", "Grace Period"]],
        },
        "name",
        order_by="creation desc"
    )


def _get_view_count_from_db(seller_profile: str, month_key: str = None) -> int:
    """Count unique RFQ views for a seller in a given month from DB.

    Deduplication: counts distinct RFQ names viewed, not total view records.

    Args:
        seller_profile: Seller Profile name.
        month_key: Year-month string. Defaults to current month.

    Returns:
        Number of unique RFQs viewed in the month.
    """
    start, end = _get_month_start_end(month_key)

    count = frappe.db.count(
        "RFQ View Log",
        filters={
            "seller": seller_profile,
            "viewed_at": ["between", [start, end]],
        }
    )
    return count or 0


def _get_cached_view_count(seller_profile: str) -> int:
    """Get the current month's view count from cache or DB.

    Falls back to DB query and populates the cache if not found.

    Args:
        seller_profile: Seller Profile name.

    Returns:
        Number of unique RFQs viewed this month.
    """
    cache_key = _get_cache_key(seller_profile)
    cached = frappe.cache.get_value(cache_key)

    if cached is not None:
        return int(cached)

    # Cache miss — query DB and populate cache
    count = _get_view_count_from_db(seller_profile)
    frappe.cache.set_value(cache_key, count, expires_in_sec=CACHE_TTL)
    return count


def _invalidate_view_cache(seller_profile: str):
    """Invalidate the cached view count for a seller.

    Args:
        seller_profile: Seller Profile name.
    """
    cache_key = _get_cache_key(seller_profile)
    frappe.cache.delete_value(cache_key)


def check_rfq_view_limit(seller_profile: str) -> Dict:
    """Check whether a seller can view more RFQs this month.

    Looks up the seller's active subscription and its package limit,
    then compares with the current month's view count.

    Args:
        seller_profile: Seller Profile name.

    Returns:
        Dict with keys: allowed, remaining, used, limit, unlimited.
    """
    subscription_name = _get_active_subscription(seller_profile)

    if not subscription_name:
        return {
            "allowed": False,
            "remaining": 0,
            "used": 0,
            "limit": 0,
            "unlimited": False,
        }

    # Get package limit
    package_name = frappe.db.get_value("Subscription", subscription_name, "subscription_package")
    if not package_name:
        return {
            "allowed": False,
            "remaining": 0,
            "used": 0,
            "limit": 0,
            "unlimited": False,
        }

    max_rfq_views = frappe.db.get_value(
        "Subscription Package", package_name, "max_rfq_views"
    ) or 0

    # 0 means unlimited
    if max_rfq_views == 0:
        used = _get_cached_view_count(seller_profile)
        return {
            "allowed": True,
            "remaining": -1,
            "used": used,
            "limit": 0,
            "unlimited": True,
        }

    used = _get_cached_view_count(seller_profile)
    remaining = max(0, max_rfq_views - used)

    return {
        "allowed": remaining > 0,
        "remaining": remaining,
        "used": used,
        "limit": max_rfq_views,
        "unlimited": False,
    }


def log_rfq_view(seller_profile: str, rfq_name: str, request=None) -> Dict:
    """Log a seller's view of an RFQ with per-month deduplication.

    If the seller has already viewed this RFQ in the current calendar month,
    no new record is created and the existing log is returned.

    Args:
        seller_profile: Seller Profile name.
        rfq_name: RFQ document name.
        request: Frappe request object (for IP/user_agent extraction).

    Returns:
        Dict with keys: logged (bool), deduplicated (bool), log_name (str or None).
    """
    month_key = _get_current_month_key()
    start, end = _get_month_start_end(month_key)

    # Deduplication check: same seller + RFQ + current month
    existing = frappe.db.get_value(
        "RFQ View Log",
        {
            "seller": seller_profile,
            "rfq": rfq_name,
            "viewed_at": ["between", [start, end]],
        },
        "name"
    )

    if existing:
        return {
            "logged": False,
            "deduplicated": True,
            "log_name": existing,
        }

    # Extract request metadata
    ip_address = ""
    user_agent = ""
    if request:
        ip_address = getattr(request, "remote_addr", "") or ""
        user_agent = (request.headers.get("User-Agent", "") if hasattr(request, "headers") else "") or ""
    elif frappe.request:
        ip_address = getattr(frappe.request, "remote_addr", "") or ""
        user_agent = (frappe.request.headers.get("User-Agent", "") if hasattr(frappe.request, "headers") else "") or ""

    # Get subscription info for the log record
    subscription_name = _get_active_subscription(seller_profile)
    package_name = None
    if subscription_name:
        package_name = frappe.db.get_value("Subscription", subscription_name, "subscription_package")

    # Create view log entry
    log = frappe.get_doc({
        "doctype": "RFQ View Log",
        "seller": seller_profile,
        "rfq": rfq_name,
        "user": frappe.session.user,
        "viewed_at": now_datetime(),
        "ip_address": ip_address,
        "user_agent": user_agent,
        "subscription": subscription_name,
        "subscription_package": package_name,
    })
    log.insert(ignore_permissions=True)
    frappe.db.commit()

    # Update cache counter
    cache_key = _get_cache_key(seller_profile)
    cached = frappe.cache.get_value(cache_key)
    if cached is not None:
        frappe.cache.set_value(cache_key, int(cached) + 1, expires_in_sec=CACHE_TTL)
    else:
        # Repopulate cache from DB
        _get_cached_view_count(seller_profile)

    return {
        "logged": True,
        "deduplicated": False,
        "log_name": log.name,
    }


@frappe.whitelist()
def get_rfq_detail_with_limit_check(rfq_name: str) -> Dict:
    """Get RFQ details after checking the seller's view limit.

    Verifies the seller has remaining quota, logs the view if allowed,
    and returns the full RFQ document data.

    Args:
        rfq_name: RFQ document name.

    Returns:
        API response with RFQ data or limit-exceeded error.
    """
    try:
        seller = frappe.db.get_value(
            "Seller Profile", {"user": frappe.session.user}, "name"
        )
        if not seller:
            return _response(False, message=_("No seller profile found for current user"))

        if not frappe.db.exists("RFQ", rfq_name):
            return _response(False, message=_("RFQ not found"))

        # Check view limit
        limit_info = check_rfq_view_limit(seller)

        if not limit_info["allowed"]:
            return _response(
                False,
                data={"limit_info": limit_info},
                message=_("RFQ view limit reached for this month. Please upgrade your subscription.")
            )

        # Log the view (with deduplication)
        log_result = log_rfq_view(seller, rfq_name, frappe.request)

        # Fetch and return RFQ details
        rfq = frappe.get_doc("RFQ", rfq_name)
        rfq_data = rfq.as_dict()

        # Refresh limit info after potential view logging
        if log_result.get("logged"):
            limit_info = check_rfq_view_limit(seller)

        return _response(True, data={
            "rfq": rfq_data,
            "limit_info": limit_info,
            "view_log": log_result,
        })

    except Exception as e:
        frappe.log_error(f"Error getting RFQ detail with limit check: {str(e)}")
        return _response(False, message=str(e))


@frappe.whitelist()
def get_rfq_view_stats(seller_profile: str = None) -> Dict:
    """Get monthly RFQ view statistics for a seller.

    Returns usage stats for the current month including total views,
    unique RFQs viewed, and limit information.

    Args:
        seller_profile: Seller Profile name. Defaults to current user's profile.

    Returns:
        API response with monthly view statistics.
    """
    try:
        if not seller_profile:
            seller_profile = frappe.db.get_value(
                "Seller Profile", {"user": frappe.session.user}, "name"
            )
        if not seller_profile:
            return _response(False, message=_("No seller profile found"))

        month_key = _get_current_month_key()
        start, end = _get_month_start_end(month_key)

        # Get unique RFQ view count (what counts toward limit)
        unique_views = _get_cached_view_count(seller_profile)

        # Get list of recently viewed RFQs
        recent_views = frappe.get_all(
            "RFQ View Log",
            filters={
                "seller": seller_profile,
                "viewed_at": ["between", [start, end]],
            },
            fields=["rfq", "rfq_title", "viewed_at", "name"],
            order_by="viewed_at desc",
            limit=20
        )

        # Get limit info
        limit_info = check_rfq_view_limit(seller_profile)

        return _response(True, data={
            "month": month_key,
            "unique_views": unique_views,
            "recent_views": recent_views,
            "limit_info": limit_info,
        })

    except Exception as e:
        frappe.log_error(f"Error getting RFQ view stats: {str(e)}")
        return _response(False, message=str(e))


@frappe.whitelist()
def get_remaining_rfq_views(seller_profile: str = None) -> Dict:
    """Get the remaining RFQ view count for the current month.

    Lightweight endpoint for quick quota checks (e.g. UI badges).

    Args:
        seller_profile: Seller Profile name. Defaults to current user's profile.

    Returns:
        API response with remaining view count.
    """
    try:
        if not seller_profile:
            seller_profile = frappe.db.get_value(
                "Seller Profile", {"user": frappe.session.user}, "name"
            )
        if not seller_profile:
            return _response(False, message=_("No seller profile found"))

        limit_info = check_rfq_view_limit(seller_profile)

        return _response(True, data={
            "remaining": limit_info["remaining"],
            "used": limit_info["used"],
            "limit": limit_info["limit"],
            "unlimited": limit_info["unlimited"],
        })

    except Exception as e:
        frappe.log_error(f"Error getting remaining RFQ views: {str(e)}")
        return _response(False, message=str(e))
