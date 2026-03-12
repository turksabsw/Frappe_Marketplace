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
- Draft/Published/Suspended workflow with verification gate
- Multi-tenant isolation via tenant field
- Server-side refetch of fetch_from fields on every validate
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime, flt


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
        self.refetch_seller_fields()
        self.validate_publish_status()
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

    def refetch_seller_fields(self):
        """
        Refetch all fetch_from fields from the linked Seller Profile server-side.

        fetch_from only auto-populates client-side; this method ensures
        server-side consistency by manually reading the seller record
        and updating all denormalized fields.
        """
        if not self.seller:
            return

        seller_data = frappe.db.get_value(
            "Seller Profile",
            self.seller,
            [
                "seller_name",
                "seller_score",
                "average_rating",
                "total_sales_count",
                "on_time_delivery_rate",
                "verification_status",
            ],
            as_dict=True,
        )

        if not seller_data:
            frappe.throw(
                _("Seller Profile {0} not found").format(self.seller)
            )

        self.seller_name = seller_data.seller_name
        self.seller_score = flt(seller_data.seller_score, 2)
        self.average_rating = flt(seller_data.average_rating, 2)
        self.total_orders = seller_data.total_sales_count or 0
        self.on_time_delivery_rate = flt(seller_data.on_time_delivery_rate)
        self.verification_status = seller_data.verification_status

    def validate_publish_status(self):
        """
        Reject transition to Published if seller is not verified.

        A Seller Transparency Profile cannot be Published unless the linked
        Seller Profile has verification_status == 'Verified'. This ensures
        only verified sellers can have publicly visible transparency profiles.
        """
        if self.status != "Published":
            return

        if self.verification_status != "Verified":
            frappe.throw(
                _("Cannot publish Transparency Profile: Seller {0} is not verified "
                  "(current status: {1}). Only verified sellers can have "
                  "published transparency profiles.").format(
                    self.seller, self.verification_status or "Unknown"
                )
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
        self.seller_score = flt(seller.seller_score, 2)
        self.average_rating = flt(seller.average_rating, 2)
        self.total_orders = seller.total_sales_count
        self.on_time_delivery_rate = flt(seller.on_time_delivery_rate)
        self.verification_status = seller.verification_status
        self.last_refreshed = now_datetime()

        self.save()
