# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

"""
Contract Template DocType Controller

Versioned contract templates with SHA256 hash verification.
Supports dynamic rule-based contract compilation via rule_engine.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint
import hashlib

from tr_contract_center.rule_engine import compile_contract, validate_markers


class ContractTemplate(Document):
    """
    Controller for Contract Template DocType.

    Implements versioning with SHA256 hash verification and
    dynamic contract compilation with rule-based clause management.
    """

    def before_insert(self):
        """Set initial values."""
        if not self.version:
            self.version = 1

        self.content_hash = self.calculate_content_hash()

    def before_save(self):
        """Handle versioning on content change and dynamic rules validation."""
        if self.has_value_changed("content"):
            self.handle_content_change()

        # Handle status change to Published
        if self.has_value_changed("status") and self.status == "Published":
            if not self.published_at:
                self.published_at = frappe.utils.now_datetime()
            if not self.published_by:
                self.published_by = frappe.session.user

        # Dynamic rules validation
        self._validate_dynamic_rules_toggle()

        if cint(self.dynamic_rules_enabled):
            validate_markers(self)

    def _validate_dynamic_rules_toggle(self):
        """Validate dynamic_rules_enabled toggle transitions."""
        if not self.has_value_changed("dynamic_rules_enabled"):
            return

        old_value = 0
        if not self.is_new():
            old_value = cint(
                frappe.db.get_value("Contract Template", self.name, "dynamic_rules_enabled")
            )

        new_value = cint(self.dynamic_rules_enabled)

        # Toggled from 0→1: validate that base_text is filled
        if old_value == 0 and new_value == 1:
            if not self.base_text or not self.base_text.strip():
                frappe.throw(
                    _("Base Text must be filled before enabling dynamic rules.")
                )

        # Toggled from 1→0: keep base_text but clear condition_rules warning
        if old_value == 1 and new_value == 0:
            frappe.msgprint(
                _("Dynamic rules disabled. Base text has been preserved. "
                  "Condition rules will not be evaluated until re-enabled."),
                indicator="blue",
            )

    def generate_preview(self):
        """
        Generate a compiled preview using compile_contract().

        Uses preview_seller if set on the template, compiles the contract
        for that seller, and stores the result in compiled_preview.
        """
        if not cint(self.dynamic_rules_enabled):
            frappe.msgprint(
                _("Dynamic rules are not enabled on this template."),
                indicator="orange",
            )
            return

        if not self.preview_seller:
            frappe.msgprint(
                _("Please set a Preview Seller to generate a preview."),
                indicator="orange",
            )
            return

        try:
            result = compile_contract(self.name, self.preview_seller)
            self.compiled_preview = result.get("compiled_content", "")
            self.save()

            frappe.msgprint(
                _("Preview generated successfully. {0} rules applied, {1} skipped.").format(
                    result.get("rules_applied", 0),
                    result.get("rules_skipped", 0),
                ),
                indicator="green",
            )
        except Exception as e:
            frappe.log_error(
                title=_("Contract Preview Generation Failed"),
                message=str(e),
            )
            frappe.throw(
                _("Failed to generate preview: {0}").format(str(e))
            )

    def handle_content_change(self):
        """Handle content changes with versioning."""
        old_hash = frappe.db.get_value("Contract Template", self.name, "content_hash")
        new_hash = self.calculate_content_hash()

        if old_hash and old_hash != new_hash:
            self.version = (self.version or 0) + 1
            self.content_hash = new_hash

            frappe.logger().info(
                f"Contract Template {self.name} content changed: v{self.version - 1} -> v{self.version}"
            )
        elif not old_hash:
            self.content_hash = new_hash

    def calculate_content_hash(self):
        """Calculate SHA256 hash of content."""
        if not self.content:
            return None

        normalized = self.content.strip()
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()

    def validate(self):
        """Validate the template."""
        self.validate_status_transition()
        self.validate_template_code()

    def validate_status_transition(self):
        """Validate status transitions."""
        if self.is_new():
            return

        old_status = frappe.db.get_value("Contract Template", self.name, "status")

        # Cannot edit published template content
        if old_status == "Published" and self.has_value_changed("content"):
            frappe.throw(
                _("Cannot edit content of Published template. Create a new version or archive first.")
            )

        # Cannot unarchive
        if old_status == "Archived" and self.status != "Archived":
            frappe.throw(_("Cannot change status of Archived template."))

    def validate_template_code(self):
        """Ensure template_code is uppercase."""
        if self.template_code:
            self.template_code = self.template_code.upper().strip().replace(" ", "_")

    def on_trash(self):
        """Prevent deletion if template has instances."""
        instance_count = frappe.db.count(
            "Contract Instance",
            filters={"template": self.name}
        )

        if instance_count > 0:
            frappe.throw(
                _("Cannot delete template '{0}' as it has {1} contract instance(s). Archive instead.").format(
                    self.title, instance_count
                )
            )


def get_published_template(template_code):
    """
    Get the published version of a template by code.

    Args:
        template_code: Template code (e.g., 'SELLER_AGREEMENT')

    Returns:
        Document: The published Contract Template or None
    """
    template_name = frappe.db.get_value(
        "Contract Template",
        {
            "template_code": template_code.upper(),
            "status": "Published"
        },
        "name"
    )

    if template_name:
        return frappe.get_doc("Contract Template", template_name)

    return None
