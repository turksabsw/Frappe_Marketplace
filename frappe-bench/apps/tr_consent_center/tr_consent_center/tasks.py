# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

"""
TR Consent Center Scheduled Tasks

These tasks are registered in hooks.py scheduler_events and run automatically.
"""

import frappe
from frappe import _
from frappe.utils import today, add_days, getdate


def check_expiring_consents():
    """
    Daily task: Check for consents expiring in the next 30 days and send notifications.

    KVKK/GDPR compliance requires notifying users before their consent expires
    so they can renew if desired.
    """
    expiry_threshold = add_days(today(), 30)

    expiring_consents = frappe.get_all(
        "Consent Record",
        filters={
            "status": "Active",
            "expiry_date": ["<=", expiry_threshold],
            "expiry_date": [">", today()]
        },
        fields=["name", "party_type", "party", "consent_topic", "expiry_date"]
    )

    for consent in expiring_consents:
        # Log the expiring consent
        frappe.get_doc({
            "doctype": "Consent Audit Log",
            "consent_record": consent.name,
            "action": "Expiry Warning",
            "action_by": "System",
            "action_date": today(),
            "details": f"Consent expiring on {consent.expiry_date}"
        }).insert(ignore_permissions=True)

        # TODO: Send notification to party
        # frappe.sendmail(...)

    if expiring_consents:
        frappe.logger().info(
            f"TR Consent Center: Found {len(expiring_consents)} consents expiring within 30 days"
        )

    frappe.db.commit()


def purge_expired_records():
    """
    Daily task: Mark expired consents as Expired and handle retention cleanup.

    Note: Actual deletion is prevented by retention policy. This task only
    updates status for consents that have passed their expiry date.
    """
    expired_consents = frappe.get_all(
        "Consent Record",
        filters={
            "status": "Active",
            "expiry_date": ["<", today()]
        },
        fields=["name"]
    )

    for consent in expired_consents:
        doc = frappe.get_doc("Consent Record", consent.name)
        doc.status = "Expired"
        doc.save(ignore_permissions=True)

        # Log the expiry
        frappe.get_doc({
            "doctype": "Consent Audit Log",
            "consent_record": consent.name,
            "action": "Auto Expired",
            "action_by": "System",
            "action_date": today(),
            "details": "Consent automatically expired by system"
        }).insert(ignore_permissions=True)

    if expired_consents:
        frappe.logger().info(
            f"TR Consent Center: Marked {len(expired_consents)} consents as expired"
        )

    frappe.db.commit()


def generate_consent_reports():
    """
    Weekly task: Generate consent statistics reports for compliance reporting.

    KVKK/GDPR requires maintaining statistics on consent grants, revocations,
    and current status distribution.
    """
    # Get consent statistics
    stats = {
        "total_active": frappe.db.count("Consent Record", {"status": "Active"}),
        "total_revoked": frappe.db.count("Consent Record", {"status": "Revoked"}),
        "total_expired": frappe.db.count("Consent Record", {"status": "Expired"}),
        "generated_date": today()
    }

    frappe.logger().info(
        f"TR Consent Center Weekly Report: "
        f"Active={stats['total_active']}, "
        f"Revoked={stats['total_revoked']}, "
        f"Expired={stats['total_expired']}"
    )

    # TODO: Store in a reporting DocType or send via email

    frappe.db.commit()


def refresh_consent_summaries():
    """
    Cron task (every 5 minutes): Refresh User Consent Summary cache for all users
    with active or recently changed consent records.

    This task ensures the User Consent Summary DocType stays in sync with
    the underlying Consent Record data, providing fast lookups for consent status.
    """
    from tr_consent_center.tradehub_compliance.doctype.user_consent_summary.user_consent_summary import (
        refresh_user_consent_summary,
    )

    # Get distinct users who have consent records
    users = frappe.get_all(
        "Consent Record",
        filters={"status": ["in", ["Active", "Pending Reacceptance"]]},
        fields=["party"],
        group_by="party"
    )

    refreshed = 0
    for entry in users:
        if entry.party:
            try:
                refresh_user_consent_summary(entry.party)
                refreshed += 1
            except Exception:
                frappe.log_error(
                    title="Consent Summary Refresh Error",
                    message=f"Failed to refresh consent summary for user: {entry.party}"
                )

    if refreshed:
        frappe.logger().info(
            f"TR Consent Center: Refreshed consent summaries for {refreshed} users"
        )

    frappe.db.commit()
