# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

"""
Messaging API Endpoints

REST API for masked messaging operations. Provides privacy-preserving
messaging between sellers and anonymous buyer segments with PII scanning.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime, cint
from typing import Dict, Any, List, Optional


def _response(success: bool, data: Any = None, message: str = None, errors: List = None) -> Dict:
    """Standard API response format."""
    return {
        "success": success,
        "data": data,
        "message": message,
        "errors": errors or []
    }


@frappe.whitelist()
def send_masked_message(
    segment: str,
    message_body: str,
    expires_at: str = None,
) -> Dict:
    """
    Send a masked message to an audience segment.

    The message body is scanned for PII (email, phone, TCKN, VKN, IBAN, URL)
    and a sanitized version is created. The original message is preserved
    in message_body, while the sanitized version goes to message_body_sanitized.

    Args:
        segment: Audience Segment document name.
        message_body: The message content to send.
        expires_at: Optional expiration datetime string.

    Returns:
        API response with:
            - success: Whether the message was created successfully.
            - pii_detected: Whether PII was found in the message.
            - message_name: The created Masked Message document name.
            - pii_details: Details of detected PII (if any).
    """
    try:
        # Validate message body
        if not message_body or not message_body.strip():
            return _response(False, message=_("Message body is required"))

        # Validate seller
        seller = _get_current_seller()
        if not seller:
            return _response(False, message=_("No seller profile found for current user"))

        # Validate segment exists and belongs to seller
        if not frappe.db.exists("Audience Segment", segment):
            return _response(False, message=_("Audience Segment not found"))

        segment_doc = frappe.get_doc("Audience Segment", segment)

        # Check segment ownership
        if segment_doc.seller != seller:
            if "System Manager" not in frappe.get_roles():
                return _response(
                    False,
                    message=_("You don't have permission to send messages to this segment")
                )

        # Check segment is active
        if not segment_doc.is_active:
            return _response(False, message=_("Cannot send messages to inactive segments"))

        # Check minimum member threshold
        if cint(segment_doc.member_count) < 3:
            return _response(
                False,
                message=_("Segment must have at least 3 members to receive messages")
            )

        # Get seller tenant
        seller_tenant = frappe.db.get_value("Seller Profile", seller, "tenant")

        # PII scan the message body before creating the document
        from tradehub_compliance.tradehub_compliance.messaging.pii_scanner import (
            scan_for_pii,
        )
        pii_results = scan_for_pii(message_body)
        has_pii = any(len(items) > 0 for items in pii_results.values())

        # Create Masked Message
        masked_msg = frappe.get_doc({
            "doctype": "Masked Message",
            "sender_type": "Seller",
            "sender": seller,
            "recipient_segment": segment,
            "message_body": message_body,
            "status": "Sent",
            "sent_at": now_datetime(),
            "expires_at": expires_at,
            "tenant": seller_tenant,
        })

        # The before_insert hook will handle PII scanning and sanitization
        masked_msg.insert()
        frappe.db.commit()

        return _response(True, data={
            "message_name": masked_msg.name,
            "pii_detected": bool(masked_msg.pii_detected),
            "pii_details": _safe_parse_json(masked_msg.pii_details_json),
            "status": masked_msg.status,
        })

    except Exception as e:
        frappe.log_error(f"Error sending masked message: {str(e)}")
        return _response(False, message=str(e))


@frappe.whitelist()
def get_masked_messages(
    segment: str = None,
    status: str = None,
    limit: int = 20,
    offset: int = 0,
) -> Dict:
    """
    Get masked messages sent by the current seller.

    Args:
        segment: Optional Audience Segment filter.
        status: Optional status filter (Draft, Sent, Delivered, Failed).
        limit: Number of results (default: 20).
        offset: Pagination offset.

    Returns:
        API response with list of masked messages.
    """
    try:
        seller = _get_current_seller()
        if not seller:
            return _response(False, message=_("No seller profile found for current user"))

        filters = {"sender": seller, "sender_type": "Seller"}

        if segment:
            filters["recipient_segment"] = segment
        if status:
            filters["status"] = status

        messages = frappe.get_all(
            "Masked Message",
            filters=filters,
            fields=[
                "name",
                "recipient_segment",
                "message_body_sanitized",
                "pii_detected",
                "status",
                "sent_at",
                "expires_at",
                "creation",
            ],
            order_by="creation desc",
            limit=limit,
            start=offset,
        )

        total = frappe.db.count("Masked Message", filters)

        return _response(True, data={"messages": messages, "total": total})

    except Exception as e:
        frappe.log_error(f"Error getting masked messages: {str(e)}")
        return _response(False, message=str(e))


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _get_current_seller() -> Optional[str]:
    """Get current user's seller profile."""
    return frappe.db.get_value("Seller Profile", {"user": frappe.session.user}, "name")


def _safe_parse_json(json_str: Optional[str]) -> Optional[Dict]:
    """
    Safely parse a JSON string, returning None on failure.

    Args:
        json_str: JSON string or None.

    Returns:
        Parsed dict/list or None.
    """
    if not json_str:
        return None

    try:
        import json
        return json.loads(json_str)
    except (json.JSONDecodeError, TypeError):
        return None
