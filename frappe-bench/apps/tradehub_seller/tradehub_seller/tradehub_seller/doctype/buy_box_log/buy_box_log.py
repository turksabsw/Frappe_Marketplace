# Copyright (c) 2026, Trade Hub and contributors
# For license information, please see license.txt

"""
Buy Box Log DocType for Trade Hub B2B Marketplace.

This module implements logging for Buy Box recalculation events. Each log
records the score changes, rank changes, and winner changes that occur
when the Buy Box algorithm recalculates scores for entries.

Key features:
- Tracks previous and new scores/ranks for audit trail
- Records winner changes for historical analysis
- Stores detailed score breakdown as JSON
- Multi-tenant data isolation via tenant field
- Supports filtering by trigger source (Manual/Scheduled/Hook/API)
"""

import frappe
from frappe import _
from frappe.model.document import Document


class BuyBoxLog(Document):
    """
    Buy Box Log DocType for recording Buy Box recalculation events.

    Each log entry captures the state change of a Buy Box Entry during
    a recalculation cycle, including score and rank changes.
    """

    def validate(self):
        """Validate Buy Box Log data before saving."""
        self.validate_buy_box_entry()
        self.validate_tenant_isolation()

    # =========================================================================
    # VALIDATION METHODS
    # =========================================================================

    def validate_buy_box_entry(self):
        """Validate that the referenced Buy Box Entry exists."""
        if not self.buy_box_entry:
            frappe.throw(_("Buy Box Entry is required"))

    def validate_tenant_isolation(self):
        """
        Validate that log belongs to user's tenant.

        Ensures multi-tenant data isolation for log records.
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
                _("Access denied: You can only access Buy Box logs in your tenant")
            )
