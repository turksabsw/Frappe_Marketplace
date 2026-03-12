# Copyright (c) 2026, Trade Hub and contributors
# For license information, please see license.txt

"""
Audience Segment DocType for Trade Hub B2B Marketplace.

This module implements audience segmentation for sellers, allowing them to
group buyers into segments based on various criteria for targeted
communication and analytics.

Key features:
- Multi-tenant data isolation via tenant field
- Manual and dynamic segment types
- Minimum member thresholds for privacy (KVKK/GDPR compliance)
- JSON-based filter criteria for dynamic segments
- Computed metrics with read-only storage
- Member count tracking
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, now_datetime


class AudienceSegment(Document):
    """
    Audience Segment DocType for seller audience management.

    Each segment groups buyers for targeted communication and analytics.
    Minimum member thresholds enforce KVKK/GDPR privacy requirements
    by preventing display or metric computation for small groups.
    """

    def validate(self):
        """Validate segment data before saving."""
        self.validate_segment_name()
        self.validate_seller()
        self.validate_thresholds()
        self.validate_tenant_isolation()
        self.update_member_count()

    def on_update(self):
        """Actions after segment is updated."""
        pass

    def on_trash(self):
        """Actions before segment is deleted."""
        pass

    # =========================================================================
    # VALIDATION METHODS
    # =========================================================================

    def validate_segment_name(self):
        """Validate segment name is not empty."""
        if not self.segment_name:
            frappe.throw(_("Segment Name is required"))

    def validate_seller(self):
        """Validate seller link exists."""
        if not self.seller:
            frappe.throw(_("Seller is required"))

    def validate_thresholds(self):
        """Validate minimum member thresholds are reasonable."""
        if cint(self.min_members_display) < 1:
            self.min_members_display = 3

        if cint(self.min_members_metrics) < 1:
            self.min_members_metrics = 5

        if cint(self.min_members_metrics) < cint(self.min_members_display):
            frappe.msgprint(
                _("Min Members for Metrics should be >= Min Members for Display"),
                indicator="orange",
                alert=True
            )

    def validate_tenant_isolation(self):
        """
        Validate that segment belongs to user's tenant.

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
                _("Access denied: You can only access segments in your tenant")
            )

    # =========================================================================
    # MEMBER MANAGEMENT
    # =========================================================================

    def update_member_count(self):
        """Update the member count based on the members table."""
        self.member_count = len(self.members) if self.members else 0

    def can_display(self):
        """
        Check if segment has enough members for display.

        Returns:
            bool: True if member count meets minimum display threshold
        """
        return cint(self.member_count) >= cint(self.min_members_display)

    def can_compute_metrics(self):
        """
        Check if segment has enough members for metrics computation.

        Returns:
            bool: True if member count meets minimum metrics threshold
        """
        return cint(self.member_count) >= cint(self.min_members_metrics)
