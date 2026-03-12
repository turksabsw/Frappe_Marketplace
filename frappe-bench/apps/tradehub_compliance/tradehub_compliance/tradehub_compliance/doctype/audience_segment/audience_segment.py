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
- Automatic segment recomputation when filter criteria change
"""

import json

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, now_datetime


# Absolute minimum members for display (KVKK/GDPR anonymity threshold)
MIN_MEMBERS_DISPLAY_FLOOR = 3


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
        self.validate_filter_json()
        self.validate_thresholds()
        self.validate_tenant_isolation()
        self.update_member_count()

    def on_update(self):
        """
        Actions after segment is updated.

        If filter_json has changed, enqueue a background job to recompute
        segment members based on the new filter criteria.
        """
        self.enqueue_recompute_if_filter_changed()

    def on_trash(self):
        """Cleanup segment members before deletion."""
        frappe.db.delete("Audience Segment Member", {"parent": self.name})

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

    def validate_filter_json(self):
        """
        Validate that filter_json is valid JSON if provided.

        For Dynamic segments, filter_json is required to define the
        criteria for automatic member population.
        """
        if not self.filter_json:
            return

        try:
            parsed = json.loads(self.filter_json)
            if not isinstance(parsed, (dict, list)):
                frappe.throw(
                    _("Filter JSON must be a valid JSON object or array")
                )
        except (json.JSONDecodeError, TypeError):
            frappe.throw(_("Filter JSON contains invalid JSON"))

    def validate_thresholds(self):
        """
        Validate minimum member thresholds.

        Enforces KVKK/GDPR anonymity requirements:
        - min_members_display must be at least 3 (privacy floor)
        - min_members_metrics must be at least 1 (defaults to 5)
        - min_members_metrics should be >= min_members_display
        """
        # Enforce absolute minimum of 3 for display (KVKK/GDPR anonymity)
        if cint(self.min_members_display) < MIN_MEMBERS_DISPLAY_FLOOR:
            self.min_members_display = MIN_MEMBERS_DISPLAY_FLOOR

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

    # =========================================================================
    # FILTER-BASED RECOMPUTATION
    # =========================================================================

    def enqueue_recompute_if_filter_changed(self):
        """
        Enqueue segment member recomputation if filter_json has changed.

        Uses frappe.enqueue to run recompute_segment_members as a
        background job, avoiding blocking the save operation.
        """
        if not self.has_value_changed("filter_json"):
            return

        if not self.filter_json:
            return

        frappe.enqueue(
            "tradehub_compliance.tradehub_compliance.doctype."
            "audience_segment.audience_segment.recompute_segment_members",
            segment_name=self.name,
            queue="default",
            enqueue_after_commit=True,
        )

        frappe.msgprint(
            _("Segment member recomputation has been queued"),
            indicator="blue",
            alert=True
        )


def recompute_segment_members(segment_name):
    """
    Recompute segment members based on filter_json criteria.

    This function is called as a background job when filter_json changes.
    It applies the filter criteria to find matching buyers and updates
    the segment's member list accordingly.

    Args:
        segment_name: Name of the Audience Segment to recompute
    """
    segment = frappe.get_doc("Audience Segment", segment_name)

    if not segment.filter_json:
        return

    try:
        filters = json.loads(segment.filter_json)
    except (json.JSONDecodeError, TypeError):
        frappe.log_error(
            title=_("Segment Recomputation Failed"),
            message=_("Invalid filter_json for segment {0}").format(segment_name)
        )
        return

    try:
        # Build query filters for Buyer Profile
        buyer_filters = {}
        if isinstance(filters, dict):
            buyer_filters = filters
        elif isinstance(filters, list):
            buyer_filters = filters

        matching_buyers = frappe.get_all(
            "Buyer Profile",
            filters=buyer_filters,
            fields=["name"],
            limit_page_length=0,
        )

        # Clear existing members
        segment.members = []

        # Add matching buyers as segment members
        for buyer in matching_buyers:
            segment.append("members", {
                "buyer": buyer.name,
                "added_at": now_datetime(),
            })

        segment.member_count = len(segment.members)
        segment.last_computed = now_datetime()
        segment.flags.ignore_validate_update_after_submit = True
        segment.save(ignore_permissions=True)

    except Exception:
        frappe.log_error(
            title=_("Segment Recomputation Failed"),
            message=_("Error recomputing members for segment {0}").format(segment_name)
        )
