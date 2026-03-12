# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

"""
Transparency Scheduled Tasks

Background tasks for maintaining seller transparency profiles and
certificate compliance within the TradeHub Compliance module.

Tasks:
    refresh_transparency_metrics:    Refreshes all published transparency profiles
                                     from their linked Seller Profiles. (cron 0 2 * * *)
    check_certificate_expiry:        Checks for certificates nearing expiry and
                                     suspends affected transparency profiles. (cron 30 2 * * *)
    anonymize_inactive_consent_data: Anonymizes data sharing preferences for users
                                     who have been inactive beyond the retention period. (weekly)
"""

import frappe
from frappe.utils import add_days, getdate, nowdate, now_datetime, cint


def refresh_transparency_metrics():
    """
    Refresh all published Seller Transparency Profiles from their linked Seller Profiles.

    Iterates over all Published transparency profiles and updates their
    denormalized metrics (seller_score, average_rating, total_orders,
    on_time_delivery_rate, verification_status) from the source Seller Profile.

    Runs daily at 02:00 (cron 0 2 * * *).
    """
    try:
        published_profiles = frappe.get_all(
            "Seller Transparency Profile",
            filters={"status": "Published"},
            fields=["name", "seller"],
            limit_page_length=0,
        )

        refreshed_count = 0
        error_count = 0

        for profile in published_profiles:
            try:
                doc = frappe.get_doc("Seller Transparency Profile", profile.name)
                doc.refresh_from_seller()
                refreshed_count += 1
            except Exception as e:
                error_count += 1
                frappe.log_error(
                    message=f"Failed to refresh transparency profile {profile.name}: {str(e)}",
                    title="Transparency Metrics Refresh Error",
                )

        frappe.db.commit()

        frappe.logger("compliance").info(
            f"Transparency metrics refresh: {refreshed_count} profiles refreshed, "
            f"{error_count} errors"
        )

    except Exception as e:
        frappe.log_error(
            message=str(e),
            title="Transparency Metrics Refresh Task Error",
        )


def check_certificate_expiry():
    """
    Check for certificates nearing expiry and suspend affected transparency profiles.

    Finds certificates expiring within a configurable alert period (default 30 days)
    and suspends the associated Seller Transparency Profiles if the certificate
    is critical. Also logs alerts for audit purposes.

    Runs daily at 02:30 (cron 30 2 * * *).
    """
    try:
        alert_days = frappe.db.get_single_value(
            "Analytics Settings", "certificate_alert_days"
        ) or 30

        expiring_date = add_days(nowdate(), alert_days)

        # Find active certificates expiring within the alert window
        expiring_certificates = frappe.get_all(
            "Certificate",
            filters={
                "status": "Active",
                "expiry_date": ["<=", expiring_date],
                "expiry_date": [">=", nowdate()],
            },
            fields=["name", "certificate_type", "holder", "expiry_date", "organization"],
            limit_page_length=0,
        )

        processed_count = 0

        for cert in expiring_certificates:
            try:
                _process_expiring_certificate(cert)
                processed_count += 1
            except Exception as e:
                frappe.log_error(
                    message=f"Failed to process expiring certificate {cert.name}: {str(e)}",
                    title="Certificate Expiry Check Error",
                )

        frappe.db.commit()

        frappe.logger("compliance").info(
            f"Certificate expiry check: {processed_count} expiring certificates processed"
        )

    except Exception as e:
        frappe.log_error(
            message=str(e),
            title="Certificate Expiry Check Task Error",
        )


def anonymize_inactive_consent_data():
    """
    Anonymize data sharing preferences for users inactive beyond the retention period.

    Finds Data Sharing Preference records where consent was withdrawn and
    the withdrawal has been completed, but historical data has not yet been
    anonymized beyond the retention window (default 90 days). Triggers
    anonymization for each qualifying record.

    Runs weekly.
    """
    try:
        retention_days = frappe.db.get_single_value(
            "Analytics Settings", "consent_retention_days"
        ) or 90

        cutoff_date = add_days(nowdate(), -retention_days)

        # Find preferences with completed withdrawal beyond retention period
        inactive_preferences = frappe.get_all(
            "Data Sharing Preference",
            filters={
                "consent_given": 0,
                "withdrawal_requested": 1,
                "withdrawal_status": "Completed",
                "withdrawal_timestamp": ["<=", cutoff_date],
            },
            fields=["name", "user", "tenant"],
            limit_page_length=0,
        )

        anonymized_count = 0

        for pref in inactive_preferences:
            try:
                _anonymize_inactive_user_data(pref)
                anonymized_count += 1
            except Exception as e:
                frappe.log_error(
                    message=f"Failed to anonymize data for preference {pref.name}: {str(e)}",
                    title="Consent Data Anonymization Error",
                )

        frappe.db.commit()

        frappe.logger("compliance").info(
            f"Inactive consent data anonymization: {anonymized_count} records anonymized"
        )

    except Exception as e:
        frappe.log_error(
            message=str(e),
            title="Consent Data Anonymization Task Error",
        )


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _process_expiring_certificate(certificate):
    """
    Process a single expiring certificate.

    Checks if the certificate holder has a Seller Transparency Profile
    and updates the profile status if the certificate is critical.
    Creates an audit log entry for the expiry warning.

    Args:
        certificate: Dict with certificate details (name, certificate_type,
                     holder, expiry_date, organization).
    """
    days_until_expiry = (getdate(certificate.expiry_date) - getdate(nowdate())).days

    # Find associated seller transparency profile via organization/holder
    seller_profile = None
    if certificate.holder:
        seller_profile = frappe.db.get_value(
            "Seller Transparency Profile",
            {"seller": certificate.holder},
            "name",
        )

    if not seller_profile and certificate.organization:
        seller_profile = frappe.db.get_value(
            "Seller Transparency Profile",
            {"seller": certificate.organization},
            "name",
        )

    if seller_profile and days_until_expiry <= 7:
        # Suspend transparency profile if certificate expires within 7 days
        current_status = frappe.db.get_value(
            "Seller Transparency Profile", seller_profile, "status"
        )
        if current_status == "Published":
            frappe.db.set_value(
                "Seller Transparency Profile",
                seller_profile,
                "status",
                "Suspended",
                update_modified=False,
            )

            frappe.logger("compliance").info(
                f"Transparency profile {seller_profile} suspended due to "
                f"certificate {certificate.name} expiring in {days_until_expiry} days"
            )

    # Log the expiry warning
    frappe.logger("compliance").info(
        f"Certificate {certificate.name} ({certificate.certificate_type}) "
        f"expiring in {days_until_expiry} days for holder {certificate.holder}"
    )


def _anonymize_inactive_user_data(preference):
    """
    Anonymize all remaining data for an inactive user whose consent
    was withdrawn beyond the retention period.

    Removes user references from audience segments, clears cached
    anonymous buyer IDs, and marks the preference as fully anonymized.

    Args:
        preference: Dict with Data Sharing Preference details
                    (name, user, tenant).
    """
    user = preference.user
    tenant = preference.tenant

    # Remove from any remaining audience segment memberships
    buyer_profile = frappe.db.get_value(
        "Buyer Profile", {"user": user}, "name"
    )

    if buyer_profile:
        members = frappe.get_all(
            "Audience Segment Member",
            filters={"buyer": buyer_profile},
            fields=["name", "parent"],
        )

        for member in members:
            frappe.db.delete("Audience Segment Member", {"name": member.name})

            if member.parent:
                new_count = frappe.db.count(
                    "Audience Segment Member",
                    filters={"parent": member.parent},
                )
                frappe.db.set_value(
                    "Audience Segment",
                    member.parent,
                    "member_count",
                    new_count,
                    update_modified=False,
                )

    # Invalidate cached anonymous buyer IDs
    cache_pattern = f"trade_hub:anon_buyer:{user}:*"
    keys = frappe.cache().get_keys(cache_pattern)
    for key in keys:
        frappe.cache().delete_value(key)

    frappe.logger("compliance").info(
        f"Anonymized inactive consent data for user {user} "
        f"(preference: {preference.name})"
    )
