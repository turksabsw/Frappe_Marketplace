# Copyright (c) 2026, Trade Hub and contributors
# For license information, please see license.txt

"""
Quick Favorite DocType for Trade Hub B2B Marketplace.

This module implements a lightweight favorites/bookmarking system that allows
buyers to quickly save references to Products, Seller Profiles, Seller Stores,
and Listings for easy access later.

Key features:
- Multi-tenant data isolation via tenant field
- Unique constraint: one favorite per user + target_type + target_reference
- Dynamic Link pattern for polymorphic target references
- Auto-populated target_name for display convenience
"""

import frappe
from frappe import _
from frappe.model.document import Document


class QuickFavorite(Document):
    """
    Quick Favorite DocType for buyer bookmarks.

    Each Quick Favorite represents a single user's bookmark of a specific
    target (Product, Seller Profile, Seller Store, or Listing). The unique
    constraint on user + target_type + target_reference prevents duplicate
    favorites.
    """

    def before_insert(self):
        """Validate uniqueness and set defaults before inserting."""
        self.validate_unique_favorite()

    def validate(self):
        """Validate Quick Favorite data before saving."""
        self.validate_target()
        self.set_target_name()
        self.validate_tenant_isolation()

    # =========================================================================
    # VALIDATION METHODS
    # =========================================================================

    def validate_unique_favorite(self):
        """
        Enforce unique constraint: user + target_type + target_reference.

        A user cannot favorite the same target more than once.
        """
        existing = frappe.db.get_value(
            "Quick Favorite",
            {
                "user": self.user,
                "target_type": self.target_type,
                "target_reference": self.target_reference,
                "name": ("!=", self.name or "")
            },
            "name"
        )

        if existing:
            frappe.throw(
                _("You have already added this {0} to your favorites").format(
                    self.target_type
                )
            )

    def validate_target(self):
        """Validate that the target reference exists."""
        if not self.target_type:
            frappe.throw(_("Target Type is required"))

        if not self.target_reference:
            frappe.throw(_("Target Reference is required"))

        if not frappe.db.exists(self.target_type, self.target_reference):
            frappe.throw(
                _("{0} '{1}' does not exist").format(
                    self.target_type, self.target_reference
                )
            )

    def set_target_name(self):
        """Auto-populate target_name from the referenced document."""
        if not self.target_reference or not self.target_type:
            return

        # Determine the title/name field based on target type
        title_field_map = {
            "Product": "product_name",
            "Seller Profile": "seller_name",
            "Seller Store": "store_name",
            "Listing": "listing_title"
        }

        title_field = title_field_map.get(self.target_type)

        if title_field:
            target_name = frappe.db.get_value(
                self.target_type, self.target_reference, title_field
            )
            if target_name:
                self.target_name = target_name
            elif not self.target_name:
                self.target_name = self.target_reference
        elif not self.target_name:
            self.target_name = self.target_reference

    def validate_tenant_isolation(self):
        """
        Validate that the favorite belongs to the user's tenant.

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
                _("Access denied: You can only manage favorites in your tenant")
            )
