# Copyright (c) 2026, Trade Hub and contributors
# For license information, please see license.txt

"""
Seller Transparency Profile DocType for Trade Hub B2B Marketplace.

This module implements the Seller Transparency Profile DocType that provides
a public-facing transparency view of seller performance metrics, certificates,
and audit reports. Each profile is linked 1:1 to a Seller Profile and fetches
key metrics (score, rating, delivery rate, verification status) directly from
the seller record.

Key Features:
- 1:1 mapping with Seller Profile (autonamed by seller field)
- Performance metrics fetched from Seller Profile (read-only)
- Certificate and audit report tables for transparency
- Draft/Published/Suspended workflow
- Multi-tenant isolation via tenant field
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class SellerTransparencyProfile(Document):
    """
    Seller Transparency Profile providing public transparency view of seller data.

    Each Seller Transparency Profile is linked to exactly one Seller Profile
    and aggregates key performance indicators, certificates, and audit reports
    for buyer visibility.
    """

    def before_insert(self):
        """Set default values before inserting a new transparency profile."""
        self.set_tenant_from_seller()

    def validate(self):
        """Validate transparency profile data before saving."""
        self.validate_unique_seller()
        self.validate_tenant_isolation()
        self.update_published_at()

    def on_update(self):
        """Actions after transparency profile is updated."""
        self.db_set("last_refreshed", now_datetime(), update_modified=False)

    # =========================================================================
    # INITIALIZATION METHODS
    # =========================================================================

    def set_tenant_from_seller(self):
        """Set tenant from the linked seller profile if not already set."""
        if self.tenant or not self.seller:
            return

        tenant = frappe.db.get_value("Seller Profile", self.seller, "tenant")
        if tenant:
            self.tenant = tenant

    # =========================================================================
    # VALIDATION METHODS
    # =========================================================================

    def validate_unique_seller(self):
        """Ensure only one transparency profile exists per seller."""
        if self.is_new():
            existing = frappe.db.exists(
                "Seller Transparency Profile",
                {"seller": self.seller, "name": ["!=", self.name]},
            )
            if existing:
                frappe.throw(
                    _("A Transparency Profile already exists for seller {0}").format(
                        self.seller
                    )
                )

    def validate_tenant_isolation(self):
        """Validate multi-tenant isolation."""
        if not self.tenant:
            self.set_tenant_from_seller()

        if not self.tenant:
            if not frappe.has_permission("Tenant", "write"):
                frappe.throw(
                    _("Transparency Profile must be associated with a tenant")
                )

    def update_published_at(self):
        """Set published_at timestamp when status changes to Published."""
        if self.status == "Published" and not self.published_at:
            self.published_at = now_datetime()

    # =========================================================================
    # PUBLIC METHODS
    # =========================================================================

    def refresh_from_seller(self):
        """
        Refresh all fetched fields from the linked Seller Profile.

        This method manually updates the fetched metrics from the seller
        record and sets the last_refreshed timestamp.
        """
        if not self.seller:
            return

        seller = frappe.get_doc("Seller Profile", self.seller)

        self.seller_name = seller.seller_name
        self.seller_score = seller.seller_score
        self.average_rating = seller.average_rating
        self.total_orders = seller.total_sales_count
        self.on_time_delivery_rate = seller.on_time_delivery_rate
        self.verification_status = seller.verification_status
        self.last_refreshed = now_datetime()

        self.save()
