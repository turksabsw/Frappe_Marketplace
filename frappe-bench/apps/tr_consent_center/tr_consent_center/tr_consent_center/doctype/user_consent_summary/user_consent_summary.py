# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class UserConsentSummary(Document):
    """
    User Consent Summary cache DocType for TR-TradeHub.

    Caches the current consent status for each user to provide fast lookups
    without querying individual Consent Records. Refreshed periodically
    via scheduled task.
    """

    def validate(self):
        """Validate the summary document."""
        self.validate_active_consents_json()

    def validate_active_consents_json(self):
        """Ensure active_consents is valid JSON if provided."""
        if self.active_consents:
            try:
                json.loads(self.active_consents)
            except (json.JSONDecodeError, TypeError):
                frappe.throw(
                    _("Active Consents must be valid JSON.")
                )


def refresh_user_consent_summary(user):
    """
    Refresh the consent summary cache for a given user.

    Queries all active Consent Records for the user and updates the
    User Consent Summary document with current consent data.

    Args:
        user: The user ID (email) to refresh the summary for.
    """
    active_records = frappe.get_all(
        "Consent Record",
        filters={
            "party": user,
            "status": "Active"
        },
        fields=["name", "consent_topic", "consent_date", "expiry_date"]
    )

    # Build active consents data
    consents_data = []
    for record in active_records:
        consents_data.append({
            "record": record.name,
            "topic": record.consent_topic,
            "consent_date": str(record.consent_date) if record.consent_date else None,
            "expiry_date": str(record.expiry_date) if record.expiry_date else None,
        })

    # Count pending reacceptance records
    pending_count = frappe.db.count(
        "Consent Record",
        filters={
            "party": user,
            "status": "Pending Reacceptance"
        }
    )

    # Get linked seller if available
    seller = None
    seller_profile = frappe.db.get_value(
        "Seller Profile",
        {"user": user},
        "name"
    )
    if seller_profile:
        seller = seller_profile

    # Update or create the summary document
    if frappe.db.exists("User Consent Summary", user):
        doc = frappe.get_doc("User Consent Summary", user)
    else:
        doc = frappe.new_doc("User Consent Summary")
        doc.user = user

    doc.active_consents = json.dumps(consents_data, default=str)
    doc.pending_reacceptance = pending_count
    doc.last_updated = now_datetime()
    doc.seller = seller
    doc.save(ignore_permissions=True)
