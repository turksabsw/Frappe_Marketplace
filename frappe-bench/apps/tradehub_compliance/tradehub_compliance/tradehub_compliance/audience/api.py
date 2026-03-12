# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

"""
Audience API Endpoints

REST API for audience segment operations. Provides anonymous member listing,
segment creation, and segment metrics with privacy thresholds.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime, cint
from typing import Dict, Any, List, Optional
import json


# Minimum members for display (KVKK/GDPR anonymity threshold)
MIN_MEMBERS_DISPLAY = 3

# Minimum members for metrics computation
MIN_MEMBERS_METRICS = 5


def _response(success: bool, data: Any = None, message: str = None, errors: List = None) -> Dict:
    """Standard API response format."""
    return {
        "success": success,
        "data": data,
        "message": message,
        "errors": errors or []
    }


@frappe.whitelist()
def get_segment_members(segment: str) -> Dict:
    """
    Get members of an audience segment as anonymous IDs.

    Returns anonymous buyer IDs (BYR-XXXXXX format) for segment members.
    Enforces minimum 3 members threshold for display (KVKK/GDPR).
    Metrics require minimum 5 members.

    Args:
        segment: Audience Segment document name.

    Returns:
        API response with:
            - members: List of anonymous buyer IDs (only if >= 3 members).
            - member_count: Total member count.
            - metrics: Segment metrics (only if >= 5 members).
            - segment_name: Segment display name.
    """
    try:
        # Validate segment exists
        if not frappe.db.exists("Audience Segment", segment):
            return _response(False, message=_("Audience Segment not found"))

        segment_doc = frappe.get_doc("Audience Segment", segment)

        # Validate seller access
        seller = _get_current_seller()
        if seller and segment_doc.seller != seller:
            # System Manager can view any segment
            if "System Manager" not in frappe.get_roles():
                return _response(
                    False,
                    message=_("You don't have permission to view this segment")
                )

        member_count = cint(segment_doc.member_count)

        result = {
            "segment_name": segment_doc.segment_name,
            "member_count": member_count,
            "segment_type": segment_doc.segment_type,
            "is_active": segment_doc.is_active,
        }

        # Enforce minimum 3 members for member list display (anonymity threshold)
        if member_count < MIN_MEMBERS_DISPLAY:
            result["members"] = []
            result["below_threshold"] = True
            result["threshold_message"] = _(
                "Segment has fewer than {0} members. Member list is hidden "
                "for privacy protection."
            ).format(MIN_MEMBERS_DISPLAY)
        else:
            # Generate anonymous IDs for each member
            anonymous_ids = _get_anonymous_member_ids(segment_doc)
            result["members"] = anonymous_ids
            result["below_threshold"] = False

        # Enforce minimum 5 members for metrics
        if member_count >= MIN_MEMBERS_METRICS:
            result["metrics"] = _get_segment_metrics(segment_doc)
        else:
            result["metrics"] = None
            if member_count >= MIN_MEMBERS_DISPLAY:
                result["metrics_message"] = _(
                    "Segment needs at least {0} members for metrics computation."
                ).format(MIN_MEMBERS_METRICS)

        return _response(True, data=result)

    except Exception as e:
        frappe.log_error(f"Error getting segment members: {str(e)}")
        return _response(False, message=str(e))


@frappe.whitelist()
def create_segment(
    segment_name: str,
    filter_json: str,
    segment_type: str = "Dynamic",
    min_members_display: int = None,
    min_members_metrics: int = None,
) -> Dict:
    """
    Create a new audience segment and compute its members.

    Creates an Audience Segment with the given filter criteria and
    triggers member computation as a background job.

    Args:
        segment_name: Name of the segment.
        filter_json: JSON string of filter criteria for Buyer Profile query.
        segment_type: Segment type (Dynamic or Manual), defaults to Dynamic.
        min_members_display: Minimum members for display (default: 3).
        min_members_metrics: Minimum members for metrics (default: 5).

    Returns:
        API response with:
            - name: Segment document name.
            - segment_name: Segment display name.
            - member_count: Number of computed members.
    """
    try:
        # Validate seller
        seller = _get_current_seller()
        if not seller:
            return _response(False, message=_("No seller profile found for current user"))

        # Validate segment_name
        if not segment_name or not segment_name.strip():
            return _response(False, message=_("Segment Name is required"))

        # Validate filter_json
        if not filter_json:
            return _response(False, message=_("Filter JSON is required for dynamic segments"))

        try:
            parsed_filters = json.loads(filter_json) if isinstance(filter_json, str) else filter_json
            if not isinstance(parsed_filters, (dict, list)):
                return _response(
                    False,
                    message=_("Filter JSON must be a valid JSON object or array")
                )
        except (json.JSONDecodeError, TypeError):
            return _response(False, message=_("Filter JSON contains invalid JSON"))

        # Get seller's tenant
        seller_tenant = frappe.db.get_value("Seller Profile", seller, "tenant")
        if not seller_tenant:
            return _response(False, message=_("Seller tenant not found"))

        # Enforce minimum thresholds
        display_threshold = max(
            cint(min_members_display) if min_members_display else MIN_MEMBERS_DISPLAY,
            MIN_MEMBERS_DISPLAY,
        )
        metrics_threshold = max(
            cint(min_members_metrics) if min_members_metrics else MIN_MEMBERS_METRICS,
            1,
        )

        # Create segment
        segment_doc = frappe.get_doc({
            "doctype": "Audience Segment",
            "segment_name": segment_name.strip(),
            "seller": seller,
            "segment_type": segment_type,
            "is_active": 1,
            "filter_json": filter_json if isinstance(filter_json, str) else json.dumps(filter_json),
            "min_members_display": display_threshold,
            "min_members_metrics": metrics_threshold,
            "tenant": seller_tenant,
        })

        segment_doc.insert()

        # Compute members immediately for the response
        _compute_segment_members(segment_doc)

        frappe.db.commit()

        return _response(True, data={
            "name": segment_doc.name,
            "segment_name": segment_doc.segment_name,
            "member_count": cint(segment_doc.member_count),
        })

    except Exception as e:
        frappe.log_error(f"Error creating segment: {str(e)}")
        return _response(False, message=str(e))


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _get_current_seller() -> Optional[str]:
    """Get current user's seller profile."""
    return frappe.db.get_value("Seller Profile", {"user": frappe.session.user}, "name")


def _get_anonymous_member_ids(segment_doc) -> List[str]:
    """
    Generate anonymous buyer IDs for all members in a segment.

    Uses HMAC-based anonymous buyer ID generation to produce
    seller-specific anonymous IDs for each buyer in the segment.

    Args:
        segment_doc: The Audience Segment document.

    Returns:
        List of anonymous buyer IDs (BYR-XXXXXX format).
    """
    from tradehub_compliance.tradehub_compliance.anonymization.anonymous_buyer import (
        generate_anonymous_buyer_id,
    )

    seller_user = frappe.db.get_value("Seller Profile", segment_doc.seller, "user")
    if not seller_user:
        return []

    anonymous_ids = []
    for member in segment_doc.members:
        if not member.buyer:
            continue

        buyer_user = frappe.db.get_value("Buyer Profile", member.buyer, "user")
        if not buyer_user:
            continue

        try:
            anon_id = generate_anonymous_buyer_id(buyer_user, seller_user)
            anonymous_ids.append(anon_id)
        except Exception:
            # Skip members where anonymous ID generation fails
            frappe.log_error(
                f"Failed to generate anonymous ID for buyer {member.buyer} in segment {segment_doc.name}"
            )

    return anonymous_ids


def _get_segment_metrics(segment_doc) -> Optional[Dict]:
    """
    Get computed metrics for a segment.

    Parses the metrics_json field from the segment document.
    Only called when member count meets the minimum metrics threshold.

    Args:
        segment_doc: The Audience Segment document.

    Returns:
        Dict of segment metrics or None.
    """
    if not segment_doc.metrics_json:
        return {"member_count": cint(segment_doc.member_count)}

    try:
        metrics = json.loads(segment_doc.metrics_json)
        if isinstance(metrics, dict):
            metrics["member_count"] = cint(segment_doc.member_count)
            return metrics
    except (json.JSONDecodeError, TypeError):
        pass

    return {"member_count": cint(segment_doc.member_count)}


def _compute_segment_members(segment_doc) -> None:
    """
    Compute segment members based on filter criteria.

    Applies filter_json to query Buyer Profile records and populates
    the segment's members table with matching buyers.

    Args:
        segment_doc: The Audience Segment document.
    """
    if not segment_doc.filter_json:
        return

    try:
        filters = json.loads(segment_doc.filter_json)
    except (json.JSONDecodeError, TypeError):
        return

    try:
        # Build query filters for Buyer Profile
        buyer_filters = {}
        if isinstance(filters, dict):
            buyer_filters = filters
        elif isinstance(filters, list):
            buyer_filters = filters

        matching_buyers = frappe.get_all(
            "Buyer Profile",
            filters=buyer_filters,
            fields=["name"],
            limit_page_length=0,
        )

        # Clear existing members
        segment_doc.members = []

        # Add matching buyers as segment members
        for buyer in matching_buyers:
            segment_doc.append("members", {
                "buyer": buyer.name,
                "added_at": now_datetime(),
            })

        segment_doc.member_count = len(segment_doc.members)
        segment_doc.last_computed = now_datetime()
        segment_doc.flags.ignore_validate_update_after_submit = True
        segment_doc.save(ignore_permissions=True)

    except Exception:
        frappe.log_error(
            f"Error computing members for segment {segment_doc.name}"
        )
