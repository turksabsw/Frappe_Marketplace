# Copyright (c) 2026, Trade Hub and contributors
# For license information, please see license.txt

"""
Masked Message DocType for Trade Hub B2B Marketplace.

This module implements privacy-preserving masked messaging between sellers
and anonymous buyer segments. Messages are scanned for PII (personally
identifiable information) and sanitized before delivery.

Key features:
- Multi-tenant data isolation via tenant field
- PII detection and sanitization of message content
- Anonymous recipient identification via HMAC-based IDs
- Audience segment-based message targeting
- Message expiration support
- Status workflow: Draft -> Sent -> Delivered / Failed
"""

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


# Valid status transitions
STATUS_TRANSITIONS = {
    "Draft": ["Sent", "Failed"],
    "Sent": ["Delivered", "Failed"],
    "Delivered": [],
    "Failed": ["Draft", "Sent"]
}


class MaskedMessage(Document):
    """
    Masked Message DocType for privacy-preserving communication.

    Each Masked Message represents a message sent from a seller or the platform
    to an audience segment, with PII detection and sanitization applied.

    Features:
    - Sender can be a Seller or Platform
    - Recipients identified by Audience Segment or anonymous ID
    - Automatic PII detection and content sanitization via pii_scanner
    - Message expiration support
    - Multi-tenant data isolation
    """

    def before_insert(self):
        """Set defaults before inserting a new masked message."""
        self.set_sent_timestamp()
        self.scan_and_sanitize_message_body()

    def validate(self):
        """Validate masked message data before saving."""
        self.validate_sender()
        self.validate_message_body()
        self.validate_status_transition()
        self.validate_tenant_isolation()

    def on_update(self):
        """Actions after masked message is saved."""
        self.clear_message_cache()

    # =========================================================================
    # DEFAULT SETTINGS
    # =========================================================================

    def set_sent_timestamp(self):
        """Set sent timestamp for new messages that are not drafts."""
        if not self.sent_at and self.status != "Draft":
            self.sent_at = now_datetime()

    def scan_and_sanitize_message_body(self):
        """
        Scan message body for PII and create a sanitized version.

        Uses the pii_scanner module to detect 6 types of PII (email, phone,
        TCKN, VKN, IBAN, URL) and populate:
        - message_body_sanitized: message with PII replaced by placeholders
        - pii_detected: flag indicating if any PII was found
        - pii_details_json: JSON details of all detected PII elements

        The original message_body is preserved unchanged.
        """
        if not self.message_body:
            return

        from tradehub_compliance.tradehub_compliance.messaging.pii_scanner import (
            sanitize_message,
            scan_for_pii,
        )

        # Scan for PII — returns dict with emails, phones, tckns, vkns, ibans, urls
        pii_results = scan_for_pii(self.message_body)

        # Check if any PII was detected
        has_pii = any(
            len(items) > 0
            for items in pii_results.values()
        )

        self.pii_detected = 1 if has_pii else 0
        self.pii_details_json = json.dumps(pii_results, ensure_ascii=False)

        # Create sanitized version with PII replaced by placeholders
        self.message_body_sanitized = sanitize_message(self.message_body)

    # =========================================================================
    # VALIDATION METHODS
    # =========================================================================

    def validate_sender(self):
        """Validate sender information based on sender type."""
        if self.sender_type == "Seller" and not self.sender:
            frappe.throw(_("Sender (Seller Profile) is required when Sender Type is Seller"))

    def validate_message_body(self):
        """Validate message body is provided and not empty."""
        if not self.message_body or not self.message_body.strip():
            frappe.throw(_("Message Body is required"))

        # Re-scan and sanitize if content changed on subsequent saves
        if self.has_value_changed("message_body"):
            self.scan_and_sanitize_message_body()

    def validate_status_transition(self):
        """Validate status transitions are valid."""
        if self.is_new():
            return

        old_status = frappe.db.get_value("Masked Message", self.name, "status")
        if old_status and old_status != self.status:
            valid_transitions = STATUS_TRANSITIONS.get(old_status, [])
            if self.status not in valid_transitions:
                frappe.throw(
                    _("Cannot change status from {0} to {1}. "
                      "Valid transitions are: {2}").format(
                        old_status, self.status,
                        ", ".join(valid_transitions) if valid_transitions else "None"
                    )
                )

    def validate_tenant_isolation(self):
        """
        Validate that masked message belongs to user's tenant.

        Ensures multi-tenant data isolation.
        """
        if not self.tenant:
            return

        # System Manager can access all tenants
        if "System Manager" in frappe.get_roles():
            return

        # Get current user's tenant
        from tradehub_core.tradehub_core.utils.tenant import get_current_tenant
        current_tenant = get_current_tenant()

        if current_tenant and self.tenant != current_tenant:
            frappe.throw(
                _("Access denied: You can only access masked messages in your tenant")
            )

    # =========================================================================
    # STATUS MANAGEMENT
    # =========================================================================

    def set_status(self, new_status):
        """
        Change the status of the masked message.

        Args:
            new_status: The new status to set

        Returns:
            bool: True if status was changed successfully
        """
        valid_transitions = STATUS_TRANSITIONS.get(self.status, [])
        if new_status not in valid_transitions:
            frappe.throw(
                _("Cannot change status from {0} to {1}").format(
                    self.status, new_status
                )
            )

        self.status = new_status

        if new_status == "Sent" and not self.sent_at:
            self.sent_at = now_datetime()

        self.save()
        return True

    def mark_as_sent(self):
        """Mark masked message as sent."""
        return self.set_status("Sent")

    def mark_as_delivered(self):
        """Mark masked message as delivered."""
        return self.set_status("Delivered")

    def mark_as_failed(self):
        """Mark masked message as failed."""
        return self.set_status("Failed")

    # =========================================================================
    # CACHE MANAGEMENT
    # =========================================================================

    def clear_message_cache(self):
        """Clear cached masked message data."""
        cache_keys = [
            f"masked_message:{self.name}",
        ]

        if self.sender:
            cache_keys.append(f"seller_masked_messages:{self.sender}")

        if self.recipient_segment:
            cache_keys.append(f"segment_masked_messages:{self.recipient_segment}")

        for key in cache_keys:
            frappe.cache().delete_value(key)
