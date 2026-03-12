# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class MappingTemplate(Document):
    """
    Mapping Template DocType for smart column mapping.

    Stores reusable column mapping configurations for import jobs.
    Templates can be global (available to all tenants/sellers) or
    scoped to a specific tenant/seller. Supports multiple import types
    and tracks mapping confidence levels.

    Features:
    - Reusable mapping configurations
    - Per-tenant/seller or global templates
    - Default template support per import type
    - Field-level match confidence tracking
    - Multiple match strategies (Historical, Exact, Normalized, Fuzzy, Manual)
    """

    def validate(self):
        """Validate the mapping template before saving."""
        self.validate_default_uniqueness()
        self.validate_scope()

    def validate_default_uniqueness(self):
        """Ensure only one default template exists per import_type + scope combination."""
        if not self.is_default:
            return

        filters = {
            "import_type": self.import_type,
            "is_default": 1,
            "name": ["!=", self.name],
        }

        if self.is_global:
            filters["is_global"] = 1
        else:
            if self.tenant:
                filters["tenant"] = self.tenant
            if self.seller:
                filters["seller"] = self.seller

        existing = frappe.db.exists("Mapping Template", filters)
        if existing:
            frappe.throw(
                _("A default mapping template already exists for this import type and scope. "
                  "Please unset the existing default first.")
            )

    def validate_scope(self):
        """Validate that global templates don't have tenant/seller set."""
        if self.is_global:
            if self.tenant or self.seller:
                frappe.throw(
                    _("Global templates cannot be assigned to a specific tenant or seller.")
                )
