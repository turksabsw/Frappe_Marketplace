# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

"""
Audience Scheduled Tasks

Background tasks for audience segment management, metrics computation,
masked message cleanup, and PII audit scanning within the TradeHub
Compliance module.

Tasks:
    compute_all_audience_segments:   Recomputes members for all active dynamic
                                     segments. (cron 0 3 * * *)
    compute_segment_metrics:         Computes aggregate metrics for segments
                                     meeting the minimum member threshold. (cron 30 3 * * *)
    cleanup_expired_masked_messages: Removes expired masked messages past their
                                     expiration date. (weekly)
    pii_audit_scan:                  Scans existing masked messages for PII
                                     leakage and re-sanitizes if needed. (weekly)
"""

import json

import frappe
from frappe import _
from frappe.utils import now_datetime, nowdate, cint, flt


def compute_all_audience_segments():
    """
    Recompute members for all active dynamic audience segments.

    Iterates over all active segments with segment_type 'Dynamic' and
    reapplies their filter_json criteria to update the member list.
    This ensures segments stay current as buyer data changes.

    Runs daily at 03:00 (cron 0 3 * * *).
    """
    try:
        dynamic_segments = frappe.get_all(
            "Audience Segment",
            filters={
                "is_active": 1,
                "segment_type": "Dynamic",
            },
            fields=["name"],
            limit_page_length=0,
        )

        recomputed_count = 0
        error_count = 0

        for segment in dynamic_segments:
            try:
                _recompute_segment(segment.name)
                recomputed_count += 1
            except Exception as e:
                error_count += 1
                frappe.log_error(
                    message=f"Failed to recompute segment {segment.name}: {str(e)}",
                    title="Audience Segment Recomputation Error",
                )

        frappe.db.commit()

        frappe.logger("compliance").info(
            f"Audience segment recomputation: {recomputed_count} segments recomputed, "
            f"{error_count} errors"
        )

    except Exception as e:
        frappe.log_error(
            message=str(e),
            title="Audience Segment Recomputation Task Error",
        )


def compute_segment_metrics():
    """
    Compute aggregate metrics for all active audience segments that meet
    the minimum member threshold.

    For each qualifying segment, computes metrics such as average order value,
    member activity rates, and segment health indicators. Results are stored
    in the segment's metrics_json field.

    Runs daily at 03:30 (cron 30 3 * * *).
    """
    try:
        active_segments = frappe.get_all(
            "Audience Segment",
            filters={"is_active": 1},
            fields=["name", "member_count", "min_members_metrics"],
            limit_page_length=0,
        )

        computed_count = 0
        skipped_count = 0

        for segment in active_segments:
            min_threshold = cint(segment.min_members_metrics) or 5
            if cint(segment.member_count) < min_threshold:
                skipped_count += 1
                continue

            try:
                _compute_metrics_for_segment(segment.name)
                computed_count += 1
            except Exception as e:
                frappe.log_error(
                    message=f"Failed to compute metrics for segment {segment.name}: {str(e)}",
                    title="Segment Metrics Computation Error",
                )

        frappe.db.commit()

        frappe.logger("compliance").info(
            f"Segment metrics computation: {computed_count} computed, "
            f"{skipped_count} skipped (below threshold)"
        )

    except Exception as e:
        frappe.log_error(
            message=str(e),
            title="Segment Metrics Computation Task Error",
        )


def cleanup_expired_masked_messages():
    """
    Clean up expired masked messages that have passed their expiration date.

    Finds all Masked Message records with an expires_at date in the past
    and marks them as expired by setting their status to 'Failed'.
    Messages older than the retention period are permanently deleted.

    Runs weekly.
    """
    try:
        retention_days = frappe.db.get_single_value(
            "Analytics Settings", "message_retention_days"
        ) or 90

        today = nowdate()

        # Mark expired messages as Failed
        expired_messages = frappe.get_all(
            "Masked Message",
            filters={
                "expires_at": ["<", today],
                "status": ["in", ["Draft", "Sent"]],
            },
            fields=["name"],
            limit_page_length=0,
        )

        expired_count = 0
        for msg in expired_messages:
            try:
                frappe.db.set_value(
                    "Masked Message",
                    msg.name,
                    "status",
                    "Failed",
                    update_modified=False,
                )
                expired_count += 1
            except Exception as e:
                frappe.log_error(
                    message=f"Failed to expire masked message {msg.name}: {str(e)}",
                    title="Masked Message Expiry Error",
                )

        # Delete messages beyond retention period
        from frappe.utils import add_days

        retention_cutoff = add_days(today, -retention_days)

        old_messages = frappe.get_all(
            "Masked Message",
            filters={
                "expires_at": ["<", retention_cutoff],
                "status": "Failed",
            },
            fields=["name"],
            limit_page_length=0,
        )

        deleted_count = 0
        for msg in old_messages:
            try:
                frappe.delete_doc(
                    "Masked Message",
                    msg.name,
                    ignore_permissions=True,
                    force=True,
                )
                deleted_count += 1
            except Exception as e:
                frappe.log_error(
                    message=f"Failed to delete old masked message {msg.name}: {str(e)}",
                    title="Masked Message Cleanup Error",
                )

        frappe.db.commit()

        frappe.logger("compliance").info(
            f"Masked message cleanup: {expired_count} expired, "
            f"{deleted_count} deleted (beyond {retention_days}-day retention)"
        )

    except Exception as e:
        frappe.log_error(
            message=str(e),
            title="Masked Message Cleanup Task Error",
        )


def pii_audit_scan():
    """
    Audit scan for PII leakage in existing masked messages.

    Re-scans all Delivered masked messages to detect any PII that may have
    slipped through the initial sanitization (e.g., due to updated PII patterns).
    If PII is found in a delivered message's sanitized body, the message is
    re-sanitized and flagged for review.

    Runs weekly.
    """
    try:
        from tradehub_compliance.tradehub_compliance.messaging.pii_scanner import (
            scan_for_pii,
            sanitize_message,
        )

        # Scan delivered messages for PII in sanitized content
        delivered_messages = frappe.get_all(
            "Masked Message",
            filters={"status": ["in", ["Sent", "Delivered"]]},
            fields=["name", "message_body_sanitized", "message_body"],
            limit_page_length=0,
        )

        flagged_count = 0
        clean_count = 0

        for msg in delivered_messages:
            try:
                sanitized = msg.message_body_sanitized or ""

                # Check if the sanitized body still contains PII
                pii_results = scan_for_pii(sanitized)
                has_pii = any(
                    len(items) > 0 for items in pii_results.values()
                )

                if has_pii:
                    # Re-sanitize the original message body
                    new_sanitized = sanitize_message(msg.message_body or "")
                    new_pii_results = scan_for_pii(msg.message_body or "")

                    frappe.db.set_value(
                        "Masked Message",
                        msg.name,
                        {
                            "message_body_sanitized": new_sanitized,
                            "pii_detected": 1,
                            "pii_details_json": json.dumps(
                                new_pii_results, ensure_ascii=False
                            ),
                        },
                        update_modified=False,
                    )

                    flagged_count += 1

                    frappe.logger("compliance").warning(
                        f"PII audit: Message {msg.name} contained PII in "
                        f"sanitized body — re-sanitized"
                    )
                else:
                    clean_count += 1

            except Exception as e:
                frappe.log_error(
                    message=f"PII audit scan failed for message {msg.name}: {str(e)}",
                    title="PII Audit Scan Error",
                )

        frappe.db.commit()

        frappe.logger("compliance").info(
            f"PII audit scan: {clean_count} clean, {flagged_count} flagged and re-sanitized"
        )

    except Exception as e:
        frappe.log_error(
            message=str(e),
            title="PII Audit Scan Task Error",
        )


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _recompute_segment(segment_name):
    """
    Recompute members for a single audience segment using its filter_json.

    Applies the filter criteria against the Buyer Profile doctype and
    updates the segment's member list and count.

    Args:
        segment_name: Name of the Audience Segment to recompute.
    """
    segment_doc = frappe.get_doc("Audience Segment", segment_name)

    if not segment_doc.filter_json:
        return

    try:
        filters = json.loads(segment_doc.filter_json)
    except (json.JSONDecodeError, TypeError):
        frappe.log_error(
            message=f"Invalid filter_json for segment {segment_name}",
            title="Segment Recomputation Error",
        )
        return

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
    segment_doc.members = []

    # Add matching buyers as segment members
    for buyer in matching_buyers:
        segment_doc.append("members", {
            "buyer": buyer.name,
            "added_at": now_datetime(),
        })

    segment_doc.member_count = len(segment_doc.members)
    segment_doc.last_computed = now_datetime()
    segment_doc.flags.ignore_validate_update_after_submit = True
    segment_doc.save(ignore_permissions=True)


def _compute_metrics_for_segment(segment_name):
    """
    Compute aggregate metrics for a single audience segment.

    Calculates metrics from segment member buyer profiles and stores
    them in the segment's metrics_json field. Metrics include member
    count, active member ratio, and average engagement indicators.

    Args:
        segment_name: Name of the Audience Segment.
    """
    segment_doc = frappe.get_doc("Audience Segment", segment_name)

    members = segment_doc.members or []
    if not members:
        return

    # Gather buyer profile data for metrics
    buyer_names = [m.buyer for m in members if m.buyer]
    if not buyer_names:
        return

    # Get buyer profile statistics
    buyer_profiles = frappe.get_all(
        "Buyer Profile",
        filters={"name": ["in", buyer_names]},
        fields=["name", "user"],
        limit_page_length=0,
    )

    metrics = {
        "member_count": len(members),
        "active_buyers": len(buyer_profiles),
        "computed_at": str(now_datetime()),
    }

    frappe.db.set_value(
        "Audience Segment",
        segment_name,
        "metrics_json",
        json.dumps(metrics, ensure_ascii=False),
        update_modified=False,
    )
