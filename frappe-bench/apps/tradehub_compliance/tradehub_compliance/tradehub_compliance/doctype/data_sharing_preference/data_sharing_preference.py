# Copyright (c) 2026, Trade Hub and contributors
# For license information, please see license.txt

"""
Data Sharing Preference DocType Controller for TradeHub Compliance.

Manages user preferences for data sharing in the marketplace, including
consent tracking, granular sharing options, and KVKK/GDPR-compliant
consent withdrawal workflow.

Key features:
- One preference record per user (autoname linked to user)
- Granular sharing controls (order history, ratings, payment metrics)
- Consent withdrawal workflow with status tracking
- Multi-tenant isolation via Tenant link
- Automatic consent timestamp management
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class DataSharingPreference(Document):
    """
    Controller for Data Sharing Preference DocType.

    Each user has at most one Data Sharing Preference record that controls
    what data can be shared with sellers and other marketplace participants.
    """

    def before_insert(self):
        """Set defaults before inserting a new record."""
        self.validate_unique_user()

    def validate(self):
        """Validate the data sharing preference record."""
        self.validate_user()
        self.validate_tenant()
        self.validate_consent_timestamp()
        self.validate_withdrawal()

    def validate_unique_user(self):
        """Ensure only one preference record exists per user."""
        existing = frappe.db.get_value(
            "Data Sharing Preference",
            {"user": self.user, "name": ("!=", self.name or "")},
            "name"
        )

        if existing:
            frappe.throw(
                _("A data sharing preference record already exists for user {0}: {1}").format(
                    self.user, existing
                )
            )

    def validate_user(self):
        """Validate that the user exists."""
        if not self.user:
            frappe.throw(_("User is required"))

        if not frappe.db.exists("User", self.user):
            frappe.throw(
                _("User {0} does not exist").format(self.user)
            )

    def validate_tenant(self):
        """Validate tenant for multi-tenant isolation."""
        if not self.tenant:
            frappe.throw(_("Tenant is required"))

        if not frappe.db.exists("Tenant", self.tenant):
            frappe.throw(
                _("Tenant {0} does not exist").format(self.tenant)
            )

    def validate_consent_timestamp(self):
        """Set consent timestamp when consent is given."""
        if self.consent_given and not self.consent_timestamp:
            self.consent_timestamp = now_datetime()

        if self.has_value_changed("consent_given") and self.consent_given:
            self.consent_timestamp = now_datetime()

    def validate_withdrawal(self):
        """Validate withdrawal fields consistency."""
        if self.withdrawal_requested:
            if not self.withdrawal_timestamp:
                self.withdrawal_timestamp = now_datetime()
            if not self.withdrawal_status:
                self.withdrawal_status = "Pending"
        else:
            # Clear withdrawal fields if not requested
            if not self.is_new() and self.has_value_changed("withdrawal_requested"):
                self.withdrawal_timestamp = None
                self.withdrawal_status = ""

    def on_update(self):
        """Actions after update."""
        if self.has_value_changed("withdrawal_requested") and self.withdrawal_requested:
            self.clear_sharing_preferences_on_withdrawal()

    def clear_sharing_preferences_on_withdrawal(self):
        """Clear all sharing preferences when withdrawal is requested."""
        frappe.db.set_value(
            "Data Sharing Preference",
            self.name,
            {
                "share_order_history": 0,
                "share_rating_history": 0,
                "share_payment_metrics": 0,
                "consent_given": 0
            },
            update_modified=False
        )
