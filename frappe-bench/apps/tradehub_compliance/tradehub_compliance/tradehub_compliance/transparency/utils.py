# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

"""
Transparency Utilities

Shared utilities for the Transparency subsystem (Tasks 120 & 121).

Primary function:
    get_disclosure_stage(buyer, seller, context) → pre_order | active_order | post_delivery

The disclosure stage controls what buyer data is visible to sellers at each
phase of their transaction relationship:

- pre_order:     No active order — minimal data, mostly anonymized
- active_order:  Active order in progress — moderate data revealed
- post_delivery: Delivery completed — full permitted data visible

Usage:
    from tradehub_compliance.tradehub_compliance.transparency.utils import get_disclosure_stage

    stage = get_disclosure_stage(buyer="BUY-00001", seller="SELLER-00001")
    # → "pre_order"

    stage = get_disclosure_stage(
        buyer="BUY-00001",
        seller="SELLER-00001",
        context={"order": "SO-00001"}
    )
    # → "active_order"
"""

import frappe
from frappe import _


# =============================================================================
# CONSTANTS
# =============================================================================

VALID_STAGES = ("pre_order", "active_order", "post_delivery")

# Default stage for unknown or missing relationships
DEFAULT_STAGE = "pre_order"

# Order statuses that indicate post-delivery stage
POST_DELIVERY_STATUSES = frozenset({
    "Completed",
    "Delivered",
    "Closed",
})

# Order statuses that indicate active-order stage
ACTIVE_ORDER_STATUSES = frozenset({
    "Submitted",
    "To Deliver and Bill",
    "To Bill",
    "To Deliver",
    "Partially Delivered",
    "Partially Billed",
    "Ordered",
    "Active",
    "In Progress",
})


# =============================================================================
# CORE FUNCTION
# =============================================================================

def get_disclosure_stage(buyer, seller, context=None):
    """
    Determine the disclosure stage for a buyer-seller relationship.

    The disclosure stage controls what data is visible to the seller about
    the buyer. It progresses through three phases based on the transaction
    history between the two parties.

    Stages:
        pre_order:     Before any order (default). Minimal data, mostly anonymized.
        active_order:  During an active order. Moderate data revealed.
        post_delivery: After delivery completed. Full permitted data visible.

    Args:
        buyer: Buyer identifier — either a User email/ID or Buyer Profile name.
        seller: Seller identifier — either a User email/ID or Seller Profile name.
        context: Optional dict with additional context:
            - stage_override (str): Force a specific stage (must be valid).
            - order (str): Specific order reference to check status against.

    Returns:
        str: One of "pre_order", "active_order", or "post_delivery".
    """
    if not buyer or not seller:
        return DEFAULT_STAGE

    # Handle explicit stage override from context
    if context and isinstance(context, dict):
        stage_override = context.get("stage_override")
        if stage_override and stage_override in VALID_STAGES:
            return stage_override

        # Determine stage from a specific order reference
        order = context.get("order")
        if order:
            return _get_stage_from_order(order)

    # Determine from buyer-seller transaction history
    return _determine_stage_from_history(buyer, seller)


# =============================================================================
# ORDER-BASED STAGE DETECTION
# =============================================================================

def _get_stage_from_order(order_name):
    """
    Determine disclosure stage from a specific order reference.

    Checks Sales Order and Purchase Order for the given name
    and maps the order status to a disclosure stage.

    Args:
        order_name: The name/ID of the order document.

    Returns:
        str: The disclosure stage derived from the order status.
    """
    if not order_name:
        return DEFAULT_STAGE

    # Check Sales Order
    if frappe.db.exists("Sales Order", order_name):
        status = frappe.db.get_value("Sales Order", order_name, "status")
        return _map_status_to_stage(status)

    # Check Purchase Order
    if frappe.db.exists("Purchase Order", order_name):
        status = frappe.db.get_value("Purchase Order", order_name, "status")
        return _map_status_to_stage(status)

    return DEFAULT_STAGE


def _map_status_to_stage(status):
    """
    Map an order status string to a disclosure stage.

    Args:
        status: The order status (e.g. "Completed", "Submitted").

    Returns:
        str: The corresponding disclosure stage.
    """
    if not status:
        return DEFAULT_STAGE

    if status in POST_DELIVERY_STATUSES:
        return "post_delivery"

    if status in ACTIVE_ORDER_STATUSES:
        return "active_order"

    return DEFAULT_STAGE


# =============================================================================
# HISTORY-BASED STAGE DETECTION
# =============================================================================

def _determine_stage_from_history(buyer, seller):
    """
    Determine disclosure stage from buyer-seller transaction history.

    Checks the most advanced stage of any transaction between the buyer
    and seller. The highest stage reached (post_delivery > active_order
    > pre_order) is returned.

    Args:
        buyer: Buyer identifier (User email/ID or Buyer Profile name).
        seller: Seller identifier (User email/ID or Seller Profile name).

    Returns:
        str: The highest disclosure stage for this buyer-seller pair.
    """
    # Check for completed deliveries first (most permissive stage)
    if _has_delivered_orders(buyer, seller):
        return "post_delivery"

    # Check for active orders
    if _has_active_orders(buyer, seller):
        return "active_order"

    return DEFAULT_STAGE


def _has_delivered_orders(buyer, seller):
    """
    Check if any completed/delivered orders exist between buyer and seller.

    Checks Sales Order for delivered status. Falls back to RFQ Quote
    with completed status if Sales Order DocType is not available.

    Args:
        buyer: Buyer identifier.
        seller: Seller identifier.

    Returns:
        bool: True if at least one delivered order exists.
    """
    # Try Sales Order first (standard ERPNext)
    if _doctype_exists("Sales Order"):
        buyer_filter = _resolve_buyer_filter_for_sales_order(buyer)
        seller_filter = _resolve_seller_filter_for_sales_order(seller)

        if buyer_filter and seller_filter:
            filters = {**buyer_filter, **seller_filter}
            filters["status"] = ["in", list(POST_DELIVERY_STATUSES)]
            filters["docstatus"] = 1

            count = frappe.db.count("Sales Order", filters=filters)
            if count > 0:
                return True

    # Fallback: check RFQ Quote with delivered/completed context
    if _doctype_exists("RFQ Quote"):
        rfq_filters = _build_rfq_quote_filters(buyer, seller)
        if rfq_filters:
            rfq_filters["status"] = ["in", ["Accepted", "Completed"]]
            rfq_filters["docstatus"] = 1

            count = frappe.db.count("RFQ Quote", filters=rfq_filters)
            if count > 0:
                return True

    return False


def _has_active_orders(buyer, seller):
    """
    Check if any active (in-progress) orders exist between buyer and seller.

    Checks Sales Order for active statuses. Falls back to RFQ Quote
    with submitted status if Sales Order DocType is not available.

    Args:
        buyer: Buyer identifier.
        seller: Seller identifier.

    Returns:
        bool: True if at least one active order exists.
    """
    # Try Sales Order first
    if _doctype_exists("Sales Order"):
        buyer_filter = _resolve_buyer_filter_for_sales_order(buyer)
        seller_filter = _resolve_seller_filter_for_sales_order(seller)

        if buyer_filter and seller_filter:
            filters = {**buyer_filter, **seller_filter}
            filters["status"] = ["in", list(ACTIVE_ORDER_STATUSES)]
            filters["docstatus"] = 1

            count = frappe.db.count("Sales Order", filters=filters)
            if count > 0:
                return True

    # Fallback: check submitted RFQ Quotes (active engagement)
    if _doctype_exists("RFQ Quote"):
        rfq_filters = _build_rfq_quote_filters(buyer, seller)
        if rfq_filters:
            rfq_filters["docstatus"] = 1

            count = frappe.db.count("RFQ Quote", filters=rfq_filters)
            if count > 0:
                return True

    return False


# =============================================================================
# FILTER RESOLUTION HELPERS
# =============================================================================

def _resolve_buyer_filter_for_sales_order(buyer):
    """
    Resolve the buyer identifier to a Sales Order filter dict.

    Handles both User email and Buyer Profile name formats.

    Args:
        buyer: Buyer identifier.

    Returns:
        dict or None: Filter dict for Sales Order query, or None if unresolvable.
    """
    if not buyer:
        return None

    # If it looks like an email, filter by customer_address owner or party
    # If it's a Buyer Profile name, resolve to customer
    if "@" in str(buyer):
        return {"owner": buyer}

    # Buyer Profile name — try to find associated customer
    if frappe.db.exists("Buyer Profile", buyer):
        user = frappe.db.get_value("Buyer Profile", buyer, "user")
        if user:
            return {"owner": user}

    return {"owner": buyer}


def _resolve_seller_filter_for_sales_order(seller):
    """
    Resolve the seller identifier to a Sales Order filter dict.

    Args:
        seller: Seller identifier.

    Returns:
        dict or None: Filter dict for Sales Order query, or None if unresolvable.
    """
    if not seller:
        return None

    # Try to resolve seller to a company/supplier name
    if frappe.db.exists("Seller Profile", seller):
        company = frappe.db.get_value("Seller Profile", seller, "company")
        if company:
            return {"company": company}

    return None


def _build_rfq_quote_filters(buyer, seller):
    """
    Build filters for RFQ Quote queries between a buyer-seller pair.

    The RFQ Quote DocType uses rfq_buyer for the buyer reference and
    seller_name for the seller reference.

    Args:
        buyer: Buyer identifier.
        seller: Seller identifier.

    Returns:
        dict or None: Filter dict for RFQ Quote query, or None if unresolvable.
    """
    filters = {}

    # Resolve buyer → rfq_buyer field
    if "@" in str(buyer):
        # Email-based: look up Buyer Profile from user
        buyer_profile = frappe.db.get_value(
            "Buyer Profile", {"user": buyer}, "name"
        )
        if buyer_profile:
            filters["rfq_buyer"] = buyer_profile
        else:
            filters["rfq_buyer"] = buyer
    else:
        filters["rfq_buyer"] = buyer

    # Resolve seller → seller_name field
    if frappe.db.exists("Seller Profile", seller):
        seller_name = frappe.db.get_value("Seller Profile", seller, "seller_name")
        if seller_name:
            filters["seller_name"] = seller_name
        else:
            filters["seller_name"] = seller
    else:
        filters["seller_name"] = seller

    return filters


# =============================================================================
# UTILITY HELPERS
# =============================================================================

def _doctype_exists(doctype_name):
    """
    Check if a DocType exists in the system (cached).

    Uses frappe.cache for performance since DocType existence
    does not change during a request lifecycle.

    Args:
        doctype_name: Name of the DocType to check.

    Returns:
        bool: True if the DocType exists.
    """
    cache_key = f"tradehub:doctype_exists:{doctype_name}"
    cached = frappe.cache().get_value(cache_key)

    if cached is not None:
        return cached

    exists = frappe.db.exists("DocType", doctype_name)
    result = bool(exists)

    # Cache for 1 hour — DocType existence rarely changes
    frappe.cache().set_value(cache_key, result, expires_in_sec=3600)

    return result


def get_visibility_rules(disclosure_stage, role=None, tenant=None):
    """
    Get active visibility rules for a given disclosure stage.

    Returns all active Buyer Visibility Rules matching the specified
    disclosure stage, optionally filtered by role and tenant. Rules
    are returned sorted by priority (highest first).

    Args:
        disclosure_stage: One of "pre_order", "active_order", "post_delivery".
        role: Optional role filter ("Seller", "Buyer", or "Both").
        tenant: Optional tenant name for multi-tenant filtering.

    Returns:
        list[dict]: List of visibility rules with field_name, visibility,
                    applies_to_role, and priority.
    """
    if disclosure_stage not in VALID_STAGES:
        frappe.throw(
            _("Invalid disclosure stage: {0}. Must be one of: {1}").format(
                disclosure_stage, ", ".join(VALID_STAGES)
            )
        )

    filters = {
        "disclosure_stage": disclosure_stage,
        "is_active": 1,
    }

    if role:
        filters["applies_to_role"] = ["in", [role, "Both", ""]]

    if tenant:
        filters["tenant"] = tenant

    return frappe.get_all(
        "Buyer Visibility Rule",
        filters=filters,
        fields=["field_name", "visibility", "applies_to_role", "priority"],
        order_by="priority desc",
    )
