# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

"""
RFQ View Log DocType Controller

Tracks which sellers have viewed which RFQs, with custom DB indexes
and row-level permission controls.
"""

import frappe
from frappe.model.document import Document


class RFQViewLog(Document):
    """
    Controller for RFQ View Log DocType.

    Records seller views on RFQs for analytics and subscription
    quota enforcement. Includes custom indexes for efficient
    querying and permission controls for data isolation.
    """

    @staticmethod
    def on_doctype_update():
        """Create database indexes for efficient querying."""
        # Index for seller view history queries (e.g. "views by seller in date range")
        frappe.db.add_index(
            "RFQ View Log",
            fields=["seller", "viewed_at"],
            index_name="idx_seller_viewed_at"
        )

        # Index for RFQ view analytics (e.g. "who viewed this RFQ and when")
        frappe.db.add_index(
            "RFQ View Log",
            fields=["rfq", "viewed_at"],
            index_name="idx_rfq_viewed_at"
        )

        # Index for duplicate/unique view checks (e.g. "has this seller viewed this RFQ")
        frappe.db.add_index(
            "RFQ View Log",
            fields=["seller", "rfq"],
            index_name="idx_seller_rfq"
        )


def get_permission_query_conditions(user):
    """
    Return SQL conditions for list queries based on user role.

    System Manager sees all records. Seller users see only their
    own records by matching the seller field to their Seller Profile.

    Args:
        user: The user for whom to generate conditions.

    Returns:
        str: SQL WHERE clause fragment, or empty string for full access.
    """
    if not user:
        user = frappe.session.user

    # System Manager and Administrator see all records
    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return ""

    # Seller users can only see their own view logs
    seller = frappe.db.get_value("Seller Profile", {"user": user}, "name")
    if seller:
        return f"`tabRFQ View Log`.`seller` = {frappe.db.escape(seller)}"

    # Users without a Seller Profile see nothing
    return "1=0"


def has_permission(doc, ptype, user):
    """
    Document-level permission check for RFQ View Log.

    Args:
        doc: The RFQ View Log document to check.
        ptype: Permission type (read, write, etc.).
        user: The user to check permission for.

    Returns:
        bool: True if the user has permission, False otherwise.
    """
    if not user:
        user = frappe.session.user

    # Administrator and System Manager have full access
    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return True

    # Seller users can only access their own view logs
    seller = frappe.db.get_value("Seller Profile", {"user": user}, "name")
    if seller and doc.seller == seller:
        return True

    return False
