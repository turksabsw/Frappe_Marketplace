# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

"""
PPR Portal API Endpoints

REST API for Platform Purchase Request operations.
Provides endpoints for sellers to browse open purchase requests,
submit offers, manage their offers, and withdraw them.
Each endpoint checks subscription status before allowing operations.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime, getdate, nowdate, add_days
from typing import Dict, Any, List, Optional
import json


def _response(success: bool, data: Any = None, message: str = None, errors: List = None) -> Dict:
    """Standard API response format."""
    return {
        "success": success,
        "data": data,
        "message": message,
        "errors": errors or []
    }


def _get_current_seller() -> Optional[str]:
    """Get current user's seller profile."""
    return frappe.db.get_value("Seller Profile", {"user": frappe.session.user}, "name")


def _check_seller_subscription(seller_profile: str) -> Dict:
    """Check seller's subscription status via cached lookup.

    Args:
        seller_profile: Seller Profile name.

    Returns:
        Dict with subscription status info.
    """
    try:
        from tradehub_marketing.tradehub_marketing.doctype.subscription.subscription import (
            get_cached_subscription_status,
        )
        return get_cached_subscription_status("Seller", seller_profile)
    except ImportError:
        # Fallback: query subscription directly if marketing module not available
        subscription = frappe.db.get_value(
            "Subscription",
            {"seller_profile": seller_profile, "status": ["in", ["Active", "Trial", "Grace Period"]]},
            ["name", "status"],
            as_dict=True,
            order_by="creation desc"
        )
        if subscription:
            return {
                "status": subscription.status,
                "subscription_name": subscription.name,
                "is_active": 1,
            }
        return {
            "status": None,
            "subscription_name": None,
            "is_active": 0,
        }


def _is_subscription_active(subscription_status: Dict) -> bool:
    """Check if the subscription status indicates an active subscription.

    Args:
        subscription_status: Dict returned by _check_seller_subscription.

    Returns:
        True if subscription is active enough to allow operations.
    """
    active_statuses = ["Active", "Trial", "Grace Period"]
    return subscription_status.get("status") in active_statuses


@frappe.whitelist()
def get_open_purchase_requests(filters: str = None) -> Dict:
    """List Platform Purchase Requests with status Published or Receiving Offers.

    Returns purchase requests that are open for seller offers.
    Checks the caller's subscription status before returning results.

    Args:
        filters: Optional JSON string with additional filters:
            - category: Filter by category
            - target_type: Filter by target type (Public/Category/Selected)
            - limit: Number of results (default 20)
            - offset: Pagination offset (default 0)

    Returns:
        API response with list of open purchase requests.
    """
    try:
        seller = _get_current_seller()
        if not seller:
            return _response(False, message=_("No seller profile found for current user"))

        # Check subscription status
        sub_status = _check_seller_subscription(seller)
        if not _is_subscription_active(sub_status):
            return _response(
                False,
                message=_("Active subscription required to browse purchase requests"),
                data={"subscription_status": sub_status.get("status")}
            )

        # Parse filters
        filter_dict = {}
        limit = 20
        offset = 0

        if filters:
            parsed = json.loads(filters) if isinstance(filters, str) else filters
            if parsed.get("category"):
                filter_dict["category"] = parsed["category"]
            if parsed.get("target_type"):
                filter_dict["target_type"] = parsed["target_type"]
            limit = parsed.get("limit", 20)
            offset = parsed.get("offset", 0)

        # Only show Published and Receiving Offers
        filter_dict["status"] = ["in", ["Published", "Receiving Offers"]]

        purchase_requests = frappe.get_all(
            "Platform Purchase Request",
            filters=filter_dict,
            fields=[
                "name", "request_code", "title", "category", "target_type",
                "closing_date", "target_delivery_date", "budget_range_min",
                "budget_range_max", "currency", "status", "total_offers_count",
                "minimum_seller_rating", "allow_partial_offers", "creation",
                "published_at"
            ],
            order_by="creation desc",
            limit=limit,
            start=offset
        )

        total = frappe.db.count("Platform Purchase Request", filter_dict)

        return _response(True, data={
            "purchase_requests": purchase_requests,
            "total": total,
        })

    except Exception as e:
        frappe.log_error(f"Error getting open purchase requests: {str(e)}")
        return _response(False, message=str(e))


@frappe.whitelist()
def submit_seller_offer(
    purchase_request: str,
    items: str,
    delivery_date: str = None,
    payment_terms: str = None,
    cover_letter: str = None
) -> Dict:
    """Create a Seller Offer for a Platform Purchase Request.

    Validates subscription status, purchase request eligibility, and
    creates the Seller Offer document with provided items.

    Args:
        purchase_request: Platform Purchase Request document name.
        items: JSON array of offer items. Each item should contain:
            - item_name: Name of the item
            - offered_quantity: Quantity offered
            - unit_price: Price per unit
            - description: Item description (optional)
        delivery_date: Proposed delivery date (YYYY-MM-DD).
        payment_terms: Proposed payment terms text.
        cover_letter: Cover letter / notes for the offer.

    Returns:
        API response with created offer details.
    """
    try:
        seller = _get_current_seller()
        if not seller:
            return _response(False, message=_("No seller profile found for current user"))

        # Check subscription status
        sub_status = _check_seller_subscription(seller)
        if not _is_subscription_active(sub_status):
            return _response(
                False,
                message=_("Active subscription required to submit offers. "
                          "Your subscription status is: {0}").format(
                    sub_status.get("status") or "None"
                ),
                data={"subscription_status": sub_status.get("status")}
            )

        # Validate purchase request exists and is accepting offers
        if not frappe.db.exists("Platform Purchase Request", purchase_request):
            return _response(False, message=_("Purchase request not found"))

        ppr = frappe.get_doc("Platform Purchase Request", purchase_request)

        if ppr.status not in ["Published", "Receiving Offers"]:
            return _response(
                False,
                message=_("This purchase request is not accepting offers. Current status: {0}").format(
                    ppr.status
                )
            )

        # Check closing date
        if ppr.closing_date and getdate(ppr.closing_date) < getdate(nowdate()):
            return _response(False, message=_("The closing date for this purchase request has passed"))

        # Check for existing offer from this seller
        existing = frappe.db.exists(
            "Seller Offer",
            {"seller": seller, "purchase_request": purchase_request, "status": ["!=", "Withdrawn"]}
        )
        if existing:
            return _response(
                False,
                message=_("You already have an active offer for this purchase request. "
                          "Withdraw the existing offer before submitting a new one."),
                data={"existing_offer": existing}
            )

        # Check minimum seller rating requirement
        if ppr.minimum_seller_rating:
            seller_rating = frappe.db.get_value("Seller Profile", seller, "seller_rating") or 0
            if seller_rating < ppr.minimum_seller_rating:
                return _response(
                    False,
                    message=_("Your seller rating ({0}) does not meet the minimum requirement ({1})").format(
                        seller_rating, ppr.minimum_seller_rating
                    )
                )

        # Create Seller Offer
        offer = frappe.get_doc({
            "doctype": "Seller Offer",
            "purchase_request": purchase_request,
            "seller": seller,
            "status": "Submitted",
            "proposed_delivery_date": delivery_date,
            "proposed_payment_terms": payment_terms,
            "cover_letter": cover_letter,
        })

        # Add items
        if items:
            items_list = json.loads(items) if isinstance(items, str) else items
            for item in items_list:
                offer.append("items", {
                    "item_name": item.get("item_name"),
                    "description": item.get("description"),
                    "offered_quantity": item.get("offered_quantity"),
                    "unit_price": item.get("unit_price"),
                })

        offer.insert()

        # Update PPR status to Receiving Offers if it was Published
        if ppr.status == "Published":
            ppr.status = "Receiving Offers"
            ppr.save()

        frappe.db.commit()

        return _response(True, data={
            "name": offer.name,
            "offer_code": offer.offer_code,
        }, message=_("Offer submitted successfully"))

    except Exception as e:
        frappe.log_error(f"Error submitting seller offer: {str(e)}")
        return _response(False, message=str(e))


@frappe.whitelist()
def get_my_offers(seller_profile: str = None, status: str = None) -> Dict:
    """List current seller's offers with optional status filter.

    Args:
        seller_profile: Seller Profile name. Defaults to current user's profile.
        status: Optional status filter (Draft/Submitted/Under Review/Accepted/Rejected/Withdrawn).

    Returns:
        API response with list of seller's offers.
    """
    try:
        seller = seller_profile or _get_current_seller()
        if not seller:
            return _response(False, message=_("No seller profile found for current user"))

        # Verify the caller owns this seller profile
        if seller_profile:
            seller_user = frappe.db.get_value("Seller Profile", seller, "user")
            if seller_user != frappe.session.user:
                return _response(False, message=_("You can only view your own offers"))

        # Check subscription status
        sub_status = _check_seller_subscription(seller)
        if not _is_subscription_active(sub_status):
            return _response(
                False,
                message=_("Active subscription required to view offers"),
                data={"subscription_status": sub_status.get("status")}
            )

        filters = {"seller": seller}
        if status:
            filters["status"] = status

        offers = frappe.get_all(
            "Seller Offer",
            filters=filters,
            fields=[
                "name", "offer_code", "purchase_request", "status",
                "total_offered_amount", "proposed_delivery_date",
                "proposed_payment_terms", "auto_score",
                "seller_rating_snapshot", "creation"
            ],
            order_by="creation desc"
        )

        # Enrich with purchase request title
        for offer in offers:
            ppr_title = frappe.db.get_value(
                "Platform Purchase Request", offer.get("purchase_request"), "title"
            )
            offer["purchase_request_title"] = ppr_title

        return _response(True, data={"offers": offers, "total": len(offers)})

    except Exception as e:
        frappe.log_error(f"Error getting seller offers: {str(e)}")
        return _response(False, message=str(e))


@frappe.whitelist()
def withdraw_offer(offer_name: str) -> Dict:
    """Withdraw a seller's offer.

    Changes the offer status to Withdrawn. Only the offer owner
    can withdraw, and only if the offer is not already Accepted or Rejected.

    Args:
        offer_name: Seller Offer document name.

    Returns:
        API response confirming withdrawal.
    """
    try:
        seller = _get_current_seller()
        if not seller:
            return _response(False, message=_("No seller profile found for current user"))

        # Check subscription status
        sub_status = _check_seller_subscription(seller)
        if not _is_subscription_active(sub_status):
            return _response(
                False,
                message=_("Active subscription required to manage offers"),
                data={"subscription_status": sub_status.get("status")}
            )

        if not frappe.db.exists("Seller Offer", offer_name):
            return _response(False, message=_("Offer not found"))

        offer = frappe.get_doc("Seller Offer", offer_name)

        # Validate ownership
        if offer.seller != seller:
            return _response(False, message=_("You don't have permission to withdraw this offer"))

        if offer.status in ["Accepted", "Rejected"]:
            return _response(
                False,
                message=_("Cannot withdraw an {0} offer").format(offer.status.lower())
            )

        if offer.status == "Withdrawn":
            return _response(False, message=_("Offer is already withdrawn"))

        offer.status = "Withdrawn"
        offer.save()
        frappe.db.commit()

        return _response(True, message=_("Offer withdrawn successfully"))

    except Exception as e:
        frappe.log_error(f"Error withdrawing offer: {str(e)}")
        return _response(False, message=str(e))
