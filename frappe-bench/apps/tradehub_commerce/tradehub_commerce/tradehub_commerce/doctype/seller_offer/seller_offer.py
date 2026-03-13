# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

"""
Seller Offer DocType Controller

Seller offers for Platform Purchase Requests with auto-scoring,
unique constraint enforcement, and subscription gate.
"""

import random
import string

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today


class SellerOffer(Document):
    """
    Controller for Seller Offer DocType.

    Validates unique seller+purchase_request constraint, enforces
    subscription gate, and calculates offer totals.
    """

    def before_insert(self):
        """Generate offer code and snapshot seller rating."""
        self._generate_offer_code()
        self._snapshot_seller_rating()

    def validate(self):
        """Validate offer data."""
        self._guard_system_fields()
        self.refetch_denormalized_fields()
        self.validate_unique_offer()
        self.validate_subscription_status()
        self.calculate_totals()

    def _guard_system_fields(self):
        """Prevent modification of system-generated fields after creation."""
        if self.is_new():
            return

        system_fields = [
            'offer_code',
            'seller_rating_snapshot',
        ]
        for field in system_fields:
            if self.has_value_changed(field):
                frappe.throw(
                    _("Field '{0}' cannot be modified after creation").format(field),
                    frappe.PermissionError
                )

    def _generate_offer_code(self):
        """Generate unique offer code in format SOF-YYYYMMDD-XXXX."""
        if self.offer_code:
            return

        date_part = today().replace("-", "")
        random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        self.offer_code = f"SOF-{date_part}-{random_part}"

    def _snapshot_seller_rating(self):
        """Snapshot the seller's current rating at offer creation time."""
        if not self.seller:
            return

        rating = frappe.db.get_value("Seller Profile", self.seller, "seller_rating")
        self.seller_rating_snapshot = flt(rating, 2)

    def refetch_denormalized_fields(self):
        """
        Re-fetch denormalized fields from source documents in validate().

        Ensures data consistency by overriding client-side values with
        authoritative data from source documents.
        """
        if self.seller:
            seller_data = frappe.db.get_value(
                "Seller Profile", self.seller,
                ["seller_name", "tenant"],
                as_dict=True
            )
            if seller_data:
                self.seller_name = seller_data.seller_name
                self.tenant = seller_data.tenant

        if self.tenant:
            tenant_name = frappe.db.get_value("Tenant", self.tenant, "tenant_name")
            if tenant_name:
                self.tenant_name = tenant_name

    def validate_unique_offer(self):
        """
        Enforce unique constraint: one offer per seller per purchase request.

        Checks frappe.db.exists for the same seller+purchase_request combination,
        excluding the current document on update.
        """
        if not self.seller or not self.purchase_request:
            return

        filters = {
            "seller": self.seller,
            "purchase_request": self.purchase_request,
        }

        # Exclude current document on update
        if not self.is_new():
            filters["name"] = ["!=", self.name]

        existing = frappe.db.exists("Seller Offer", filters)
        if existing:
            frappe.throw(
                _("Seller already has an offer for this Purchase Request. "
                  "Please withdraw the existing offer before creating a new one.")
            )

    def validate_subscription_status(self):
        """
        Subscription gate: block offers from sellers with Suspended/Cancelled subscriptions.

        Checks the seller's active subscription status. If Suspended or Cancelled,
        the seller is not allowed to submit an offer.
        """
        if not self.seller:
            return

        # Only check on new offers or status change to Submitted
        if not self.is_new() and not self.has_value_changed("status"):
            return

        seller_user = frappe.db.get_value("Seller Profile", self.seller, "user")
        if not seller_user:
            return

        # Check for active subscription linked to this seller
        subscription = frappe.db.get_value(
            "Subscription",
            {"subscriber": seller_user, "docstatus": ["<", 2]},
            ["status"],
            as_dict=True,
            order_by="creation desc"
        )

        if subscription and subscription.status in ("Suspended", "Cancelled"):
            frappe.throw(
                _("Your subscription is {0}. You cannot submit offers "
                  "until your subscription is reactivated.").format(
                    subscription.status
                )
            )

    def calculate_totals(self):
        """
        Calculate total offered amount from child items.

        Sums the total_price field from all Seller Offer Item rows.
        """
        total = 0
        for item in self.get("items", []):
            item.total_price = flt(
                flt(item.offered_quantity, 2) * flt(item.unit_price, 2), 2
            )
            total += flt(item.total_price, 2)

        self.total_offered_amount = flt(total, 2)

    @staticmethod
    def on_doctype_update():
        """Create database indexes for performance."""
        frappe.db.add_index(
            "Seller Offer",
            fields=["seller", "purchase_request"],
            index_name="idx_seller_pr"
        )
        frappe.db.add_index(
            "Seller Offer",
            fields=["purchase_request", "status", "auto_score"],
            index_name="idx_pr_status_score"
        )
        frappe.db.add_index(
            "Seller Offer",
            fields=["seller", "status"],
            index_name="idx_seller_status"
        )

    @frappe.whitelist()
    def withdraw(self):
        """Withdraw the offer."""
        if self.status in ["Accepted", "Rejected"]:
            frappe.throw(
                _("Cannot withdraw an {0} offer").format(self.status.lower())
            )

        self.status = "Withdrawn"
        self.save()

        return {"success": True, "message": _("Offer withdrawn")}
