# Copyright (c) 2026, Trade Hub and contributors
# For license information, please see license.txt

"""
Buyer Visibility Rule DocType for Trade Hub B2B Marketplace.

This module implements rules that control what buyer information is visible
at different stages of a transaction. Rules support anonymization and hiding
of specific fields based on disclosure stages and user roles, ensuring
KVKK/GDPR privacy compliance.

Key features:
- Stage-based visibility control (pre_order, active_order, post_delivery)
- Field-level visibility settings (visible, hidden, anonymized)
- Role-based rule application (Seller, Buyer, Both)
- Priority-based rule ordering for conflict resolution
- Multi-tenant data isolation via Tenant link
- Duplicate active rule detection per field_name + disclosure_stage
"""

import re

import frappe
from frappe import _
from frappe.model.document import Document


# Valid field name pattern: lowercase letters, digits, underscores (snake_case)
FIELD_NAME_PATTERN = re.compile(r'^[a-z][a-z0-9_]*$')


class BuyerVisibilityRule(Document):
    """
    Buyer Visibility Rule DocType for controlling field-level visibility.

    Each rule defines whether a specific field should be visible, hidden,
    or anonymized at a given disclosure stage. Rules are evaluated by
    priority (higher values take precedence) and can target specific roles.
    """

    def validate(self):
        """Validate Buyer Visibility Rule data before saving."""
        self.validate_rule_name()
        self.validate_field_name()
        self.validate_is_active()
        self.validate_priority()
        self.validate_tenant_isolation()

    # =========================================================================
    # VALIDATION METHODS
    # =========================================================================

    def validate_rule_name(self):
        """Validate that rule_name is provided and not empty."""
        if not self.rule_name or not self.rule_name.strip():
            frappe.throw(_("Rule Name is required"))

    def validate_field_name(self):
        """
        Validate that field_name is provided, not empty, and follows
        the expected snake_case naming convention for DocType field names.
        """
        if not self.field_name or not self.field_name.strip():
            frappe.throw(_("Field Name is required"))

        field_name = self.field_name.strip()
        self.field_name = field_name

        if not FIELD_NAME_PATTERN.match(field_name):
            frappe.throw(
                _("Field Name '{0}' is invalid. Use lowercase letters, digits, and "
                  "underscores only (e.g., 'company_name', 'email')").format(field_name)
            )

    def validate_is_active(self):
        """
        Validate is_active flag and warn about duplicate active rules.

        If this rule is active, check for existing active rules that target
        the same field_name and disclosure_stage combination within the
        same tenant. Multiple active rules are allowed (resolved by priority)
        but a warning helps administrators avoid unintended conflicts.
        """
        if not self.is_active:
            return

        filters = {
            "field_name": self.field_name,
            "disclosure_stage": self.disclosure_stage,
            "is_active": 1,
            "name": ("!=", self.name or ""),
        }

        if self.tenant:
            filters["tenant"] = self.tenant

        existing = frappe.db.get_value(
            "Buyer Visibility Rule",
            filters,
            ["name", "rule_name", "priority"],
            as_dict=True
        )

        if existing:
            frappe.msgprint(
                _("Another active rule '{0}' (priority {1}) already exists for "
                  "field '{2}' at stage '{3}'. The rule with higher priority will "
                  "take precedence.").format(
                    existing.rule_name,
                    existing.priority,
                    self.field_name,
                    self.disclosure_stage
                ),
                indicator="orange",
                alert=True
            )

    def validate_priority(self):
        """Validate that priority is a non-negative integer."""
        if self.priority is not None and self.priority < 0:
            frappe.throw(_("Priority must be a non-negative integer"))

    def validate_tenant_isolation(self):
        """
        Validate that rule belongs to user's tenant.

        Ensures multi-tenant data isolation for visibility rules.
        """
        if not self.tenant:
            return

        # System Manager can access all tenants
        if "System Manager" in frappe.get_roles():
            return

        from tradehub_core.tradehub_core.utils.tenant import get_current_tenant
        current_tenant = get_current_tenant()

        if current_tenant and self.tenant != current_tenant:
            frappe.throw(
                _("Access denied: You can only access Buyer Visibility Rules in your tenant")
            )
