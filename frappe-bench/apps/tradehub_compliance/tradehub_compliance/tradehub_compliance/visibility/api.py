# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

"""
Visibility API Endpoints

REST API for buyer visibility operations. Provides anonymized buyer profile
views for sellers using visibility rules and HMAC-based anonymous buyer IDs.
"""

import frappe
from frappe import _
from frappe.utils import flt
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


@frappe.whitelist()
def get_seller_view(buyer: str, context: str = None) -> Dict:
    """
    Get an anonymized buyer profile view for the current seller.

    Returns the buyer's transparency profile data filtered through
    visibility rules for the current disclosure stage, plus an
    HMAC-based anonymous buyer ID.

    Args:
        buyer: Buyer Profile name or User email/ID.
        context: Optional JSON string with context parameters:
            - seller (str): Override seller (defaults to current user's seller profile).
            - order (str): Specific order reference to determine disclosure stage.
            - stage_override (str): Force a specific disclosure stage.

    Returns:
        API response with:
            - anonymized_profile: Dict of buyer data filtered by visibility rules.
            - disclosure_stage: Current disclosure stage for this buyer-seller pair.
            - anonymous_id: HMAC-based anonymous buyer ID (BYR-XXXXXX format).
    """
    try:
        # Resolve context
        ctx = _parse_context(context)

        # Resolve seller from current user or context override
        seller = ctx.get("seller") or _get_current_seller()
        if not seller:
            return _response(False, message=_("No seller profile found for current user"))

        # Resolve buyer identifier
        buyer_profile = _resolve_buyer_profile(buyer)
        if not buyer_profile:
            return _response(False, message=_("Buyer profile not found"))

        # Get buyer and seller user identifiers for anonymous ID generation
        buyer_user = frappe.db.get_value("Buyer Profile", buyer_profile, "user")
        seller_user = frappe.db.get_value("Seller Profile", seller, "user")

        if not buyer_user or not seller_user:
            return _response(False, message=_("Unable to resolve user identifiers"))

        # Check data sharing consent
        consent_given = _check_data_sharing_consent(buyer_user)

        # Determine disclosure stage
        from tradehub_compliance.tradehub_compliance.transparency.utils import (
            get_disclosure_stage,
        )
        disclosure_stage = get_disclosure_stage(buyer_profile, seller, ctx)

        # Get visibility rules for this stage
        from tradehub_compliance.tradehub_compliance.transparency.utils import (
            get_visibility_rules,
        )
        seller_tenant = frappe.db.get_value("Seller Profile", seller, "tenant")
        visibility_rules = get_visibility_rules(
            disclosure_stage,
            role="Seller",
            tenant=seller_tenant,
        )

        # Build anonymized profile from buyer transparency data
        anonymized_profile = _build_anonymized_profile(
            buyer_profile, visibility_rules, consent_given
        )

        # Generate anonymous buyer ID
        from tradehub_compliance.tradehub_compliance.anonymization.anonymous_buyer import (
            generate_anonymous_buyer_id,
        )
        anonymous_id = generate_anonymous_buyer_id(buyer_user, seller_user)

        # Add anonymous ID to profile
        anonymized_profile["anonymous_id"] = anonymous_id

        return _response(True, data={
            "anonymized_profile": anonymized_profile,
            "disclosure_stage": disclosure_stage,
            "anonymous_id": anonymous_id,
        })

    except Exception as e:
        frappe.log_error(f"Error getting seller view: {str(e)}")
        return _response(False, message=str(e))


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _parse_context(context: Optional[str]) -> Dict:
    """
    Parse the context parameter from JSON string to dict.

    Args:
        context: JSON string or None.

    Returns:
        Parsed dict or empty dict.
    """
    if not context:
        return {}

    try:
        parsed = json.loads(context) if isinstance(context, str) else context
        if isinstance(parsed, dict):
            return parsed
    except (json.JSONDecodeError, TypeError):
        pass

    return {}


def _get_current_seller() -> Optional[str]:
    """Get current user's seller profile."""
    return frappe.db.get_value("Seller Profile", {"user": frappe.session.user}, "name")


def _resolve_buyer_profile(buyer: str) -> Optional[str]:
    """
    Resolve a buyer identifier to a Buyer Profile name.

    Handles both direct Buyer Profile names and User email/ID formats.

    Args:
        buyer: Buyer Profile name or User email/ID.

    Returns:
        Buyer Profile name or None if not found.
    """
    if not buyer:
        return None

    # Check if it's a direct Buyer Profile name
    if frappe.db.exists("Buyer Profile", buyer):
        return buyer

    # Try to resolve from User email/ID
    buyer_profile = frappe.db.get_value(
        "Buyer Profile", {"user": buyer}, "name"
    )
    return buyer_profile


def _check_data_sharing_consent(buyer_user: str) -> bool:
    """
    Check if the buyer has given data sharing consent.

    If consent is not given or has been withdrawn, only minimal
    anonymized data should be returned.

    Args:
        buyer_user: The buyer's User email/ID.

    Returns:
        True if consent is given and not withdrawn.
    """
    pref = frappe.db.get_value(
        "Data Sharing Preference",
        {"user": buyer_user},
        ["consent_given", "withdrawal_requested"],
        as_dict=True,
    )

    if not pref:
        # No preference record — default to no consent (privacy-first)
        return False

    return bool(pref.consent_given) and not bool(pref.withdrawal_requested)


def _build_anonymized_profile(
    buyer_profile: str,
    visibility_rules: List[Dict],
    consent_given: bool,
) -> Dict:
    """
    Build an anonymized buyer profile based on visibility rules.

    Fetches the buyer's transparency profile data and applies visibility
    rules to determine which fields are visible, hidden, or anonymized.

    Args:
        buyer_profile: Buyer Profile document name.
        visibility_rules: List of visibility rule dicts from get_visibility_rules().
        consent_given: Whether the buyer has given data sharing consent.

    Returns:
        Dict of anonymized buyer profile data.
    """
    # Build a rule lookup: field_name → visibility setting
    # Rules are already sorted by priority (highest first), so first match wins
    rule_map = {}
    for rule in visibility_rules:
        field_name = rule.get("field_name")
        if field_name not in rule_map:
            rule_map[field_name] = rule.get("visibility", "hidden")

    # Get buyer transparency profile data
    transparency_profile = frappe.db.get_value(
        "Buyer Transparency Profile",
        {"buyer": buyer_profile},
        [
            "name",
            "buyer_tier",
            "total_orders",
            "payment_on_time_rate",
            "average_order_value",
            "member_since",
            "disclosure_stage",
        ],
        as_dict=True,
    )

    if not transparency_profile:
        # No transparency profile — return minimal data
        return {
            "has_profile": False,
            "buyer_tier": "Unknown",
        }

    # Define profile fields and their display values
    profile_fields = {
        "buyer_tier": transparency_profile.buyer_tier or "Unknown",
        "total_orders": transparency_profile.total_orders or 0,
        "payment_on_time_rate": flt(transparency_profile.payment_on_time_rate),
        "average_order_value": flt(transparency_profile.average_order_value),
        "member_since": str(transparency_profile.member_since) if transparency_profile.member_since else None,
    }

    # If consent not given, only return minimal anonymized data
    if not consent_given:
        return {
            "has_profile": True,
            "consent_given": False,
            "buyer_tier": _anonymize_value("buyer_tier", profile_fields.get("buyer_tier")),
        }

    # Apply visibility rules
    result = {"has_profile": True, "consent_given": True}

    for field_name, value in profile_fields.items():
        visibility = rule_map.get(field_name, "visible")

        if visibility == "visible":
            result[field_name] = value
        elif visibility == "anonymized":
            result[field_name] = _anonymize_value(field_name, value)
        # "hidden" fields are omitted from the result

    return result


def _anonymize_value(field_name: str, value: Any) -> Any:
    """
    Return an anonymized version of a field value.

    Replaces actual values with safe ranges or generic indicators
    that preserve aggregate usefulness without revealing exact data.

    Args:
        field_name: The field name being anonymized.
        value: The original value.

    Returns:
        Anonymized version of the value.
    """
    if value is None:
        return None

    # Numeric fields → round to bucket ranges
    if field_name == "total_orders":
        n = int(value) if value else 0
        if n == 0:
            return "0"
        elif n < 5:
            return "1-5"
        elif n < 20:
            return "5-20"
        elif n < 50:
            return "20-50"
        else:
            return "50+"

    if field_name == "payment_on_time_rate":
        rate = flt(value)
        if rate >= 95:
            return "Excellent"
        elif rate >= 80:
            return "Good"
        elif rate >= 60:
            return "Fair"
        else:
            return "Needs Improvement"

    if field_name == "average_order_value":
        return "***"

    if field_name == "member_since":
        return "***"

    if field_name == "buyer_tier":
        return str(value) if value else "Unknown"

    # Default: mask the value
    return "***"
