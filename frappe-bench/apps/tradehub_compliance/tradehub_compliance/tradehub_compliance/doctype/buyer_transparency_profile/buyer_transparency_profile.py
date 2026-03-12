# Copyright (c) 2026, Trade Hub and contributors
# For license information, please see license.txt

"""
Buyer Transparency Profile DocType for Trade Hub B2B Marketplace.

This module implements the Buyer Transparency Profile DocType that provides
a transparency view of buyer metrics for sellers. Each profile is linked
1:1 to a Buyer Profile and fetches key metrics (total orders, payment
on-time rate, average order value, membership date, buyer tier) directly
from the buyer record.

Key Features:
- 1:1 mapping with Buyer Profile (autonamed by buyer field)
- Performance metrics fetched from Buyer Profile (read-only)
- Disclosure stage controls what sellers can see at each order phase
- Multi-tenant isolation via tenant field
"""

import frappe
from frappe import _
from frappe.model.document import Document


class BuyerTransparencyProfile(Document):
    """
    Buyer Transparency Profile providing transparency view of buyer data for sellers.

    Each Buyer Transparency Profile is linked to exactly one Buyer Profile
    and aggregates key performance indicators for seller visibility,
    controlled by the disclosure_stage field.
    """

    def before_insert(self):
        """Set default values before inserting a new transparency profile."""
        self.set_tenant_from_buyer()

    def validate(self):
        """Validate transparency profile data before saving."""
        self.validate_unique_buyer()
        self.validate_tenant_isolation()

    # =========================================================================
    # INITIALIZATION METHODS
    # =========================================================================

    def set_tenant_from_buyer(self):
        """Set tenant from the linked buyer profile if not already set."""
        if self.tenant or not self.buyer:
            return

        tenant = frappe.db.get_value("Buyer Profile", self.buyer, "tenant")
        if tenant:
            self.tenant = tenant

    # =========================================================================
    # VALIDATION METHODS
    # =========================================================================

    def validate_unique_buyer(self):
        """Ensure only one transparency profile exists per buyer."""
        if self.is_new():
            existing = frappe.db.exists(
                "Buyer Transparency Profile",
                {"buyer": self.buyer, "name": ["!=", self.name]},
            )
            if existing:
                frappe.throw(
                    _("A Transparency Profile already exists for buyer {0}").format(
                        self.buyer
                    )
                )

    def validate_tenant_isolation(self):
        """Validate multi-tenant isolation."""
        if not self.tenant:
            self.set_tenant_from_buyer()

        if not self.tenant:
            if not frappe.has_permission("Tenant", "write"):
                frappe.throw(
                    _("Transparency Profile must be associated with a tenant")
                )

    # =========================================================================
    # PUBLIC METHODS
    # =========================================================================

    def refresh_from_buyer(self):
        """
        Refresh all fetched fields from the linked Buyer Profile.

        This method manually updates the fetched metrics from the buyer
        record and sets the values accordingly.
        """
        if not self.buyer:
            return

        buyer = frappe.get_doc("Buyer Profile", self.buyer)

        self.total_orders = buyer.total_orders
        self.payment_on_time_rate = buyer.payment_on_time_rate
        self.average_order_value = buyer.average_order_value
        self.member_since = buyer.creation
        self.buyer_tier = buyer.buyer_level_name

        self.save()
