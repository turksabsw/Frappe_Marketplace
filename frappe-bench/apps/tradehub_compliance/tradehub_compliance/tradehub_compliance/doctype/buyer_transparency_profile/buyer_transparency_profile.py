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
- Disclosure stage computed via get_disclosure_stage() from transparency utils
- Multi-tenant isolation via tenant field
- Server-side refetch of fetch_from fields on every validate
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


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
        self.refetch_buyer_fields()
        self.compute_disclosure_stage()

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

    def refetch_buyer_fields(self):
        """
        Refetch all fetch_from fields from the linked Buyer Profile server-side.

        fetch_from only auto-populates client-side; this method ensures
        server-side consistency by manually reading the buyer record
        and updating all denormalized fields.
        """
        if not self.buyer:
            return

        buyer_data = frappe.db.get_value(
            "Buyer Profile",
            self.buyer,
            [
                "total_orders",
                "payment_on_time_rate",
                "average_order_value",
                "creation",
                "buyer_level_name",
            ],
            as_dict=True,
        )

        if not buyer_data:
            frappe.throw(
                _("Buyer Profile {0} not found").format(self.buyer)
            )

        self.total_orders = buyer_data.total_orders or 0
        self.payment_on_time_rate = flt(buyer_data.payment_on_time_rate)
        self.average_order_value = flt(buyer_data.average_order_value)
        self.member_since = buyer_data.creation
        self.buyer_tier = buyer_data.buyer_level_name

    def compute_disclosure_stage(self):
        """
        Compute the current disclosure stage for this buyer.

        Uses the shared get_disclosure_stage() utility to determine the
        appropriate disclosure stage. At the profile level (no specific
        seller context), we compute the highest stage reached across all
        of the buyer's transaction history:

        - pre_order:     No active orders — minimal data, mostly anonymized
        - active_order:  Active order in progress — moderate data revealed
        - post_delivery: Delivery completed — full permitted data visible

        The per-seller stage is computed on-the-fly by the visibility API.
        """
        if not self.buyer:
            self.disclosure_stage = "pre_order"
            return

        buyer_user = frappe.db.get_value("Buyer Profile", self.buyer, "user")
        if not buyer_user:
            self.disclosure_stage = "pre_order"
            return

        self.disclosure_stage = _get_buyer_highest_stage(buyer_user)

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
        self.payment_on_time_rate = flt(buyer.payment_on_time_rate)
        self.average_order_value = flt(buyer.average_order_value)
        self.member_since = buyer.creation
        self.buyer_tier = buyer.buyer_level_name

        self.save()


def _get_buyer_highest_stage(buyer_user):
    """
    Determine the highest disclosure stage for a buyer across all sellers.

    Checks the buyer's order history to find the most advanced stage
    reached with any seller. This is used for the profile-level
    disclosure_stage field.

    Args:
        buyer_user: The User email/ID associated with the buyer.

    Returns:
        str: The highest disclosure stage ("pre_order", "active_order",
             or "post_delivery").
    """
    from tradehub_compliance.tradehub_compliance.transparency.utils import (
        POST_DELIVERY_STATUSES,
        ACTIVE_ORDER_STATUSES,
        DEFAULT_STAGE,
    )

    # Check for any completed deliveries (most permissive stage)
    if frappe.db.exists("DocType", "Sales Order"):
        delivered_count = frappe.db.count(
            "Sales Order",
            filters={
                "owner": buyer_user,
                "status": ["in", list(POST_DELIVERY_STATUSES)],
                "docstatus": 1,
            },
        )
        if delivered_count > 0:
            return "post_delivery"

    # Check for any active orders
    if frappe.db.exists("DocType", "Sales Order"):
        active_count = frappe.db.count(
            "Sales Order",
            filters={
                "owner": buyer_user,
                "status": ["in", list(ACTIVE_ORDER_STATUSES)],
                "docstatus": 1,
            },
        )
        if active_count > 0:
            return "active_order"

    # Fallback: check RFQ Quotes
    if frappe.db.exists("DocType", "RFQ Quote"):
        buyer_profile = frappe.db.get_value(
            "Buyer Profile", {"user": buyer_user}, "name"
        )
        if buyer_profile:
            # Check for completed RFQ Quotes
            completed_count = frappe.db.count(
                "RFQ Quote",
                filters={
                    "rfq_buyer": buyer_profile,
                    "status": ["in", ["Accepted", "Completed"]],
                    "docstatus": 1,
                },
            )
            if completed_count > 0:
                return "post_delivery"

            # Check for active RFQ Quotes
            active_rfq_count = frappe.db.count(
                "RFQ Quote",
                filters={
                    "rfq_buyer": buyer_profile,
                    "docstatus": 1,
                },
            )
            if active_rfq_count > 0:
                return "active_order"

    return DEFAULT_STAGE
