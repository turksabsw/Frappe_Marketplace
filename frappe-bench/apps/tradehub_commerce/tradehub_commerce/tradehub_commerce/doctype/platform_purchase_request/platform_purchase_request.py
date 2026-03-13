# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

"""
Platform Purchase Request DocType Controller

Main Platform Purchase Request document with workflow management.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, now_datetime, getdate, today


class PlatformPurchaseRequest(Document):
    """
    Controller for Platform Purchase Request DocType.

    Workflow: Draft -> Published -> Receiving Offers -> Evaluation -> Awarded -> Closed/Cancelled
    """

    def before_insert(self):
        """Generate request code and set created_by_user."""
        if not self.request_code:
            self.request_code = self._generate_request_code()
        if not self.created_by_user:
            self.created_by_user = frappe.session.user

    def _generate_request_code(self):
        """Generate unique request code."""
        # Format: PPR-YYYYMMDD-XXXX (random suffix)
        import random
        import string
        date_part = today().replace("-", "")
        random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        return f"PPR-{date_part}-{random_part}"

    def validate(self):
        """Validate Platform Purchase Request data."""
        self._guard_system_fields()
        self.validate_status_transition()
        self.validate_dates()
        self.validate_budget_range()
        self.validate_minimum_seller_rating()
        self.calculate_totals()

    def _guard_system_fields(self):
        """Prevent modification of system-generated fields after creation."""
        if self.is_new():
            return

        system_fields = [
            'request_code',
            'published_at',
            'total_offers_count',
            'created_by_user',
        ]
        for field in system_fields:
            if self.has_value_changed(field):
                frappe.throw(
                    _("Field '{0}' cannot be modified after creation").format(field),
                    frappe.PermissionError
                )

    def validate_status_transition(self):
        """Validate status transitions."""
        if self.is_new():
            return

        old_status = frappe.db.get_value("Platform Purchase Request", self.name, "status")
        if old_status == self.status:
            return

        valid_transitions = {
            "Draft": ["Published", "Cancelled"],
            "Published": ["Receiving Offers", "Closed", "Cancelled"],
            "Receiving Offers": ["Evaluation", "Closed", "Cancelled"],
            "Evaluation": ["Awarded", "Closed", "Cancelled"],
            "Awarded": ["Closed"],
            "Closed": [],
            "Cancelled": []
        }

        if self.status not in valid_transitions.get(old_status, []):
            frappe.throw(
                _("Invalid status transition from {0} to {1}").format(
                    old_status, self.status
                )
            )

    def validate_dates(self):
        """Validate closing date and target delivery date."""
        if self.closing_date and self.status in ["Draft", "Published"]:
            if getdate(self.closing_date) < getdate(today()):
                frappe.throw(_("Closing date must be in the future"))

        if self.closing_date and self.target_delivery_date:
            if getdate(self.target_delivery_date) < getdate(self.closing_date):
                frappe.throw(
                    _("Target delivery date must be after the closing date")
                )

    def validate_budget_range(self):
        """Validate budget range consistency."""
        self.budget_range_min = flt(self.budget_range_min, 2)
        self.budget_range_max = flt(self.budget_range_max, 2)

        if flt(self.budget_range_min, 2) > 0 and flt(self.budget_range_max, 2) > 0:
            if flt(self.budget_range_min, 2) > flt(self.budget_range_max, 2):
                frappe.throw(_("Minimum budget cannot exceed maximum budget"))

    def validate_minimum_seller_rating(self):
        """Validate minimum seller rating is within valid range."""
        if self.minimum_seller_rating:
            rating = flt(self.minimum_seller_rating, 1)
            if rating < 0 or rating > 5:
                frappe.throw(_("Minimum seller rating must be between 0 and 5"))

    def calculate_totals(self):
        """
        Calculate and normalize numeric fields with flt precision.

        Ensures all currency and quantity fields use flt(value, 2) for
        financial precision.
        """
        # Normalize item quantities and target prices
        if self.items:
            for item in self.items:
                item.required_quantity = flt(item.required_quantity, 2)
                item.target_unit_price = flt(item.target_unit_price, 2)

    def before_save(self):
        """Handle status-specific logic."""
        if self.has_value_changed("status"):
            self._handle_status_change()

    def _handle_status_change(self):
        """Handle status change side effects."""
        if self.status == "Published":
            self.published_at = now_datetime()

    def on_update(self):
        """Post-save processing."""
        self._update_offers_count()

    def _update_offers_count(self):
        """Update offer statistics."""
        # This could update a denormalized offer count field
        pass

    @staticmethod
    def on_doctype_update():
        """Create database indexes for performance."""
        frappe.db.add_index(
            "Platform Purchase Request",
            fields=["status", "closing_date"],
            index_name="idx_status_closing"
        )
        frappe.db.add_index(
            "Platform Purchase Request",
            fields=["category", "status"],
            index_name="idx_category_status"
        )

    @frappe.whitelist()
    def publish(self):
        """Publish the Platform Purchase Request."""
        if self.status != "Draft":
            frappe.throw(_("Only draft purchase requests can be published"))

        if not self.closing_date:
            frappe.throw(_("Closing date is required to publish"))

        self.status = "Published"
        self.save()

        return {"success": True, "message": _("Purchase request published successfully")}

    @frappe.whitelist()
    def close(self, reason=None):
        """Close the Platform Purchase Request."""
        if self.status in ["Closed", "Cancelled"]:
            frappe.throw(_("Purchase request is already closed"))

        self.status = "Closed"
        self.save()

        return {"success": True, "message": _("Purchase request closed")}

    @frappe.whitelist()
    def cancel_request(self, reason=None):
        """Cancel the Platform Purchase Request."""
        if self.status in ["Awarded", "Closed"]:
            frappe.throw(_("Cannot cancel purchase request in current status"))

        self.status = "Cancelled"
        self.save()

        return {"success": True, "message": _("Purchase request cancelled")}
