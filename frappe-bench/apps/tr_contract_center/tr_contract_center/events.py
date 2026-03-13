# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

"""
TR Contract Center Document Events
"""

import frappe
from frappe import _


def contract_instance_on_update(doc, method):
    """
    Handle Contract Instance on_update event.

    - Create revision record on significant changes
    - Validate wet signature has PDF
    """
    # Check if status changed to Signed
    if doc.has_value_changed("status") and doc.status == "Signed":
        # Validate wet signature has PDF
        if doc.signature_method == "Wet" and not doc.signed_pdf:
            frappe.throw(
                _("Wet signature requires a signed PDF document to be uploaded")
            )

        # Set signed_at if not set
        if not doc.signed_at:
            doc.signed_at = frappe.utils.now_datetime()

    # Create revision record for significant changes
    if not doc.is_new() and doc.has_value_changed("content_snapshot"):
        create_revision(doc)


def on_seller_profile_update(doc, method):
    """
    Handle Seller Profile on_update event.

    Finds all active Contract Templates with dynamic_rules_enabled=1
    and enqueues a background job to recompile each template for this seller.
    """
    templates = frappe.get_all(
        "Contract Template",
        filters={
            "dynamic_rules_enabled": 1,
            "docstatus": ["!=", 2],
        },
        pluck="name",
    )

    if not templates:
        return

    for template_name in templates:
        frappe.enqueue(
            "tr_contract_center.rule_engine.compile_contract",
            template_name=template_name,
            seller_name=doc.name,
            queue="default",
            enqueue_after_commit=True,
        )

    frappe.logger("events").info(
        f"Enqueued recompilation of {len(templates)} template(s) for seller '{doc.name}'"
    )


def on_subscription_update(doc, method):
    """
    Handle Subscription on_update event.

    When a subscription's package changes, triggers recompilation of all
    active Contract Templates with dynamic_rules_enabled=1 for the
    associated seller.
    """
    if not doc.has_value_changed("subscription_package"):
        return

    seller_name = getattr(doc, "seller_profile", None)
    if not seller_name:
        return

    templates = frappe.get_all(
        "Contract Template",
        filters={
            "dynamic_rules_enabled": 1,
            "docstatus": ["!=", 2],
        },
        pluck="name",
    )

    if not templates:
        return

    for template_name in templates:
        frappe.enqueue(
            "tr_contract_center.rule_engine.compile_contract",
            template_name=template_name,
            seller_name=seller_name,
            queue="default",
            enqueue_after_commit=True,
        )

    frappe.logger("events").info(
        f"Enqueued recompilation of {len(templates)} template(s) for seller '{seller_name}' "
        f"due to subscription package change"
    )


def create_revision(doc):
    """Create a revision record for the contract."""
    # Get current revision number
    last_revision = frappe.db.get_value(
        "Contract Revision",
        {"contract_instance": doc.name},
        "revision_number",
        order_by="revision_number desc"
    ) or 0

    frappe.get_doc({
        "doctype": "Contract Revision",
        "contract_instance": doc.name,
        "revision_number": last_revision + 1,
        "content_snapshot": doc.content_snapshot,
        "created_by": frappe.session.user,
        "revision_notes": f"Content updated at {frappe.utils.now_datetime()}"
    }).insert(ignore_permissions=True)
