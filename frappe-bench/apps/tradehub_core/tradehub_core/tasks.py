# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

"""
TradeHub Core Scheduled Tasks.

This module contains scheduled task functions for buyer-side operations:
- calculate_customer_grades: Weekly task to calculate buyer grades (A-F)
- recalculate_buyer_metrics: Weekly task to recalculate buyer metrics
- calculate_buyer_scores: Weekly task to run buyer scoring pipeline
- buyer_level_tasks: Weekly task to evaluate and update buyer levels
- update_buyer_kpi_template_stats: Weekly task to update Buyer KPI Template statistics
- refresh_user_segments: Hourly task to evaluate and sync User Segment membership

All scheduled jobs use Redis lock pattern to prevent concurrent execution.
"""

from datetime import datetime

import frappe
from frappe import _
from frappe.utils import nowdate


def calculate_customer_grades():
    """
    Weekly task to calculate customer grades (A-F) for all active buyers.

    Scheduled: Sunday 05:00 (via hooks.py cron).

    Steps:
    1. Acquire Redis lock to prevent concurrent execution
    2. Get all active buyer profiles
    3. For each buyer:
       - Create a Customer Grade record
       - Run the grading pipeline (collect, normalize, weight, aggregate, grade)
       - Buyers with < 3 orders get provisional grade 'C'
       - Finalize the grade record
    4. Update Seller Customer Grade records for per-seller views
    5. Commit every 100 records

    Uses per-buyer try/except to ensure a single failure doesn't block others.
    """
    lock_key = "calculate_customer_grades_lock"
    if frappe.cache().get_value(lock_key):
        frappe.log_error(
            "calculate_customer_grades already running",
            "Scheduler Lock"
        )
        return

    frappe.cache().set_value(lock_key, 1, expires_in_sec=3600)
    try:
        _run_customer_grading()
    finally:
        frappe.cache().delete_value(lock_key)


def _run_customer_grading():
    """Internal function to run the customer grading pipeline for all active buyers."""
    if not frappe.db.exists("DocType", "Customer Grade"):
        return

    if not frappe.db.exists("DocType", "Buyer Profile"):
        return

    # Get all active buyer profiles
    buyers = frappe.get_all(
        "Buyer Profile",
        filters={"status": "Active"},
        fields=["name"]
    )

    if not buyers:
        frappe.logger().info("No active buyers found for grading")
        return

    frappe.logger().info(
        f"Starting customer grade calculation for {len(buyers)} buyers..."
    )

    processed = 0
    errors = 0
    grade_period = datetime.now().strftime("%Y-W%V")

    for buyer in buyers:
        try:
            _calculate_grade_for_buyer(buyer.name, grade_period)
            processed += 1

            # Commit every 100 records
            if processed % 100 == 0:
                frappe.db.commit()

        except Exception as e:
            errors += 1
            frappe.log_error(
                message=f"Grade calculation failed for buyer {buyer.name}: {str(e)}",
                title="Customer Grade Error"
            )

    frappe.db.commit()

    frappe.logger().info(
        f"Customer grade calculation complete. Processed: {processed}, Errors: {errors}"
    )


def _calculate_grade_for_buyer(buyer_name, grade_period):
    """Calculate and finalize a grade for a single buyer.

    Creates a new Customer Grade record, runs the grading pipeline,
    and finalizes it. For buyers with fewer than 3 orders, a provisional
    grade of 'C' (score 55.0) is assigned automatically by the pipeline.

    Args:
        buyer_name: Buyer Profile name.
        grade_period: Period identifier (e.g., '2024-W05').
    """
    # Create a new Customer Grade record
    grade = frappe.get_doc({
        "doctype": "Customer Grade",
        "buyer": buyer_name,
        "grade_type": "Weekly",
        "grade_period": grade_period,
        "calculation_date": nowdate(),
        "status": "Calculating",
    })

    # Run the grading pipeline (handles min 3 orders threshold + provisional grade)
    grade.run_grading_pipeline()

    # Insert and finalize
    grade.insert(ignore_permissions=True)
    grade.finalize(user="Administrator")

    # Update Seller Customer Grade records for this buyer
    _update_seller_customer_grades(buyer_name, grade)


def _update_seller_customer_grades(buyer_name, customer_grade):
    """Update Seller Customer Grade records for all sellers who trade with this buyer.

    For each seller that has an existing Seller Customer Grade record with this
    buyer, update the platform grade and score from the latest Customer Grade.

    Args:
        buyer_name: Buyer Profile name.
        customer_grade: The finalized Customer Grade document.
    """
    if not frappe.db.exists("DocType", "Seller Customer Grade"):
        return

    # Get all existing seller customer grade records for this buyer
    seller_grades = frappe.get_all(
        "Seller Customer Grade",
        filters={
            "buyer": buyer_name,
            "status": "Active"
        },
        fields=["name"]
    )

    for sg in seller_grades:
        try:
            sg_doc = frappe.get_doc("Seller Customer Grade", sg.name)
            sg_doc.update_from_platform_grade(customer_grade)
            sg_doc.save(ignore_permissions=True)
        except Exception as e:
            frappe.log_error(
                message=f"Failed to update Seller Customer Grade {sg.name}: {str(e)}",
                title="Seller Customer Grade Update Error"
            )


def recalculate_buyer_metrics():
    """
    Weekly task to recalculate buyer metrics for all active buyers.

    Scheduled: Sunday 03:00 (via hooks.py cron).

    Steps:
    1. Acquire Redis lock to prevent concurrent execution
    2. Get all active buyer profiles
    3. For each buyer, recalculate order stats and derived metrics
    4. Commit every 100 records

    Uses per-buyer try/except to ensure a single failure doesn't block others.
    """
    lock_key = "recalculate_buyer_metrics_lock"
    if frappe.cache().get_value(lock_key):
        frappe.log_error(
            "recalculate_buyer_metrics already running",
            "Scheduler Lock"
        )
        return

    frappe.cache().set_value(lock_key, 1, expires_in_sec=3600)
    try:
        _run_buyer_metrics_recalculation()
    finally:
        frappe.cache().delete_value(lock_key)


def _run_buyer_metrics_recalculation():
    """Internal function to recalculate buyer metrics for all active buyers."""
    if not frappe.db.exists("DocType", "Buyer Profile"):
        return

    buyers = frappe.get_all(
        "Buyer Profile",
        filters={"status": "Active"},
        fields=["name"]
    )

    if not buyers:
        frappe.logger().info("No active buyers found for metrics recalculation")
        return

    frappe.logger().info(
        f"Starting buyer metrics recalculation for {len(buyers)} buyers..."
    )

    processed = 0
    errors = 0

    for buyer in buyers:
        try:
            _recalculate_metrics_for_buyer(buyer.name)
            processed += 1

            # Commit every 100 records
            if processed % 100 == 0:
                frappe.db.commit()

        except Exception as e:
            errors += 1
            frappe.log_error(
                message=f"Metrics recalculation failed for buyer {buyer.name}: {str(e)}",
                title="Buyer Metrics Recalculation Error"
            )

    frappe.db.commit()

    frappe.logger().info(
        f"Buyer metrics recalculation complete. Processed: {processed}, Errors: {errors}"
    )


def _recalculate_metrics_for_buyer(buyer_name):
    """Recalculate metrics for a single buyer.

    Updates order stats and derived fields (return_rate, feedback_rate,
    dispute_rate, cancellation_rate, payment_pattern) on the Buyer Profile
    using frappe.db.set_value to avoid triggering full validation hooks.

    Args:
        buyer_name: Buyer Profile name.
    """
    from tradehub_core.tradehub_core.utils.safe_math import safe_divide

    buyer = frappe.get_doc("Buyer Profile", buyer_name)

    # Recalculate order statistics
    orders = frappe.get_all(
        "Marketplace Order",
        filters={"buyer": buyer_name, "status": ["not in", ["Cancelled", "Draft"]]},
        fields=["name", "grand_total", "status", "creation"]
    )

    total_orders = len(orders)
    total_spent = sum(o.grand_total or 0 for o in orders)
    average_order_value = safe_divide(total_spent, total_orders)

    # Calculate return rate
    return_count = 0
    if frappe.db.exists("DocType", "Return Request"):
        return_count = frappe.db.count(
            "Return Request",
            {"buyer": buyer_name, "status": ["not in", ["Cancelled", "Draft"]]}
        )
    return_rate = safe_divide(return_count, total_orders) * 100 if total_orders else 0

    # Calculate dispute rate
    dispute_rate = 0
    if frappe.db.exists("DocType", "Dispute"):
        dispute_count = frappe.db.count(
            "Dispute",
            {"buyer": buyer_name}
        )
        dispute_rate = safe_divide(dispute_count, total_orders) * 100 if total_orders else 0

    # Calculate cancellation rate
    cancelled_orders = frappe.db.count(
        "Marketplace Order",
        {"buyer": buyer_name, "status": "Cancelled"}
    )
    all_orders = frappe.db.count(
        "Marketplace Order",
        {"buyer": buyer_name}
    )
    cancellation_rate = safe_divide(cancelled_orders, all_orders) * 100 if all_orders else 0

    # Calculate feedback rate
    feedback_count = 0
    if frappe.db.exists("DocType", "Seller Feedback"):
        feedback_count = frappe.db.count(
            "Seller Feedback",
            {"buyer": buyer_name}
        )
    feedback_rate = safe_divide(feedback_count, total_orders) * 100 if total_orders else 0

    # Derive payment pattern
    payment_on_time_rate = buyer.payment_on_time_rate or 0
    if total_orders == 0:
        payment_pattern = "New"
    elif payment_on_time_rate >= 95:
        payment_pattern = "On-Time"
    elif payment_on_time_rate >= 80:
        payment_pattern = "Mixed"
    else:
        payment_pattern = "Late"

    # Update using set_value to avoid triggering full validate (which guards system fields)
    frappe.db.set_value("Buyer Profile", buyer_name, {
        "total_orders": total_orders,
        "total_spent": total_spent,
        "average_order_value": round(average_order_value, 2),
        "return_rate": round(return_rate, 2),
        "feedback_rate": round(feedback_rate, 2),
        "dispute_rate": round(dispute_rate, 2),
        "cancellation_rate": round(cancellation_rate, 2),
        "payment_pattern": payment_pattern,
    }, update_modified=False)


def calculate_buyer_scores():
    """
    Weekly task to calculate buyer scores using the 8-step scoring pipeline.

    Scheduled: Sunday 04:00 (via hooks.py cron).

    Steps:
    1. Acquire Redis lock to prevent concurrent execution
    2. Get all active buyer profiles
    3. For each buyer, run the scoring pipeline and persist results
    4. Commit every 100 records

    Uses per-buyer try/except to ensure a single failure doesn't block others.
    """
    lock_key = "calculate_buyer_scores_lock"
    if frappe.cache().get_value(lock_key):
        frappe.log_error(
            "calculate_buyer_scores already running",
            "Scheduler Lock"
        )
        return

    frappe.cache().set_value(lock_key, 1, expires_in_sec=3600)
    try:
        _run_buyer_score_calculation()
    finally:
        frappe.cache().delete_value(lock_key)


def _run_buyer_score_calculation():
    """Internal function to calculate scores for all active buyers."""
    if not frappe.db.exists("DocType", "Buyer Profile"):
        return

    buyers = frappe.get_all(
        "Buyer Profile",
        filters={"status": "Active"},
        fields=["name"]
    )

    if not buyers:
        frappe.logger().info("No active buyers found for score calculation")
        return

    frappe.logger().info(
        f"Starting buyer score calculation for {len(buyers)} buyers..."
    )

    processed = 0
    errors = 0

    for buyer in buyers:
        try:
            _calculate_score_for_buyer(buyer.name)
            processed += 1

            # Commit every 100 records
            if processed % 100 == 0:
                frappe.db.commit()

        except Exception as e:
            errors += 1
            frappe.log_error(
                message=f"Score calculation failed for buyer {buyer.name}: {str(e)}",
                title="Buyer Score Calculation Error"
            )

    frappe.db.commit()

    frappe.logger().info(
        f"Buyer score calculation complete. Processed: {processed}, Errors: {errors}"
    )


def _calculate_score_for_buyer(buyer_name):
    """Calculate and persist score for a single buyer.

    Uses the buyer scoring engine to calculate the score and writes
    buyer_score, buyer_score_trend, and last_score_date to the Buyer Profile.

    Args:
        buyer_name: Buyer Profile name.
    """
    from tradehub_core.tradehub_core.scoring.engine import calculate_buyer_score_for_profile

    calculate_buyer_score_for_profile(buyer_name)


def buyer_level_tasks():
    """
    Weekly task to evaluate and update buyer levels for all active buyers.

    Scheduled: Sunday 04:00 (via hooks.py cron).

    Steps:
    1. Acquire Redis lock to prevent concurrent execution
    2. Get all active buyer profiles
    3. Get all active buyer levels ordered by rank (highest first)
    4. For each buyer, evaluate qualification for each level
    5. Update buyer_level if qualification changes
    6. Commit every 100 records

    Uses per-buyer try/except to ensure a single failure doesn't block others.
    """
    lock_key = "buyer_level_tasks_lock"
    if frappe.cache().get_value(lock_key):
        frappe.log_error(
            "buyer_level_tasks already running",
            "Scheduler Lock"
        )
        return

    frappe.cache().set_value(lock_key, 1, expires_in_sec=3600)
    try:
        _run_buyer_level_evaluation()
    finally:
        frappe.cache().delete_value(lock_key)


def _run_buyer_level_evaluation():
    """Internal function to evaluate buyer levels for all active buyers."""
    if not frappe.db.exists("DocType", "Buyer Profile"):
        return

    if not frappe.db.exists("DocType", "Buyer Level"):
        return

    buyers = frappe.get_all(
        "Buyer Profile",
        filters={"status": "Active"},
        fields=["name", "buyer_level"]
    )

    if not buyers:
        frappe.logger().info("No active buyers found for level evaluation")
        return

    # Get all active levels ordered by rank (highest first for top-down evaluation)
    levels = frappe.get_all(
        "Buyer Level",
        filters={"status": "Active"},
        fields=["name", "level_rank"],
        order_by="level_rank desc"
    )

    if not levels:
        frappe.logger().info("No active buyer levels found")
        return

    frappe.logger().info(
        f"Starting buyer level evaluation for {len(buyers)} buyers..."
    )

    processed = 0
    errors = 0

    for buyer in buyers:
        try:
            _evaluate_level_for_buyer(buyer, levels)
            processed += 1

            # Commit every 100 records
            if processed % 100 == 0:
                frappe.db.commit()

        except Exception as e:
            errors += 1
            frappe.log_error(
                message=f"Level evaluation failed for buyer {buyer.name}: {str(e)}",
                title="Buyer Level Evaluation Error"
            )

    frappe.db.commit()

    frappe.logger().info(
        f"Buyer level evaluation complete. Processed: {processed}, Errors: {errors}"
    )


def _evaluate_level_for_buyer(buyer, levels):
    """Evaluate and update level for a single buyer.

    Iterates through levels from highest to lowest rank and assigns the
    highest qualifying level. If no level qualifies, assigns the default
    level.

    Args:
        buyer: Buyer dict with name and buyer_level fields.
        levels: List of active Buyer Level records ordered by rank desc.
    """
    new_level = None

    for level in levels:
        level_doc = frappe.get_doc("Buyer Level", level.name)
        if level_doc.evaluate_buyer(buyer.name):
            new_level = level.name
            break

    # If no level qualifies, try default level
    if not new_level:
        default_level = frappe.db.get_value(
            "Buyer Level",
            {"is_default": 1, "status": "Active"},
            "name"
        )
        new_level = default_level

    # Update if changed
    if new_level and new_level != buyer.buyer_level:
        frappe.db.set_value(
            "Buyer Profile", buyer.name, "buyer_level", new_level,
            update_modified=False
        )


def update_buyer_kpi_template_stats():
    """
    Weekly task to update statistics on Buyer KPI Template records.

    Scheduled: Sunday 06:00 (via hooks.py cron).

    Steps:
    1. Acquire Redis lock to prevent concurrent execution
    2. Get all active Buyer KPI Templates
    3. For each template, recalculate usage_count and average_score
    4. Update buyer counts on Buyer Level records

    Uses per-template try/except to ensure a single failure doesn't block others.
    """
    lock_key = "update_buyer_kpi_template_stats_lock"
    if frappe.cache().get_value(lock_key):
        frappe.log_error(
            "update_buyer_kpi_template_stats already running",
            "Scheduler Lock"
        )
        return

    frappe.cache().set_value(lock_key, 1, expires_in_sec=3600)
    try:
        _run_buyer_kpi_template_stats_update()
    finally:
        frappe.cache().delete_value(lock_key)


def _run_buyer_kpi_template_stats_update():
    """Internal function to update Buyer KPI Template statistics."""
    # Update Buyer KPI Template stats
    if frappe.db.exists("DocType", "Buyer KPI Template"):
        templates = frappe.get_all(
            "Buyer KPI Template",
            filters={"status": "Active"},
            fields=["name"]
        )

        frappe.logger().info(
            f"Updating statistics for {len(templates)} Buyer KPI Templates..."
        )

        for template in templates:
            try:
                _update_template_stats(template.name)
            except Exception as e:
                frappe.log_error(
                    message=f"Template stats update failed for {template.name}: {str(e)}",
                    title="Buyer KPI Template Stats Error"
                )

    # Update Buyer Level counts
    if frappe.db.exists("DocType", "Buyer Level"):
        levels = frappe.get_all("Buyer Level", pluck="name")

        frappe.logger().info(
            f"Updating buyer counts for {len(levels)} Buyer Levels..."
        )

        for level_name in levels:
            try:
                level_doc = frappe.get_doc("Buyer Level", level_name)
                level_doc.update_buyer_count()
            except Exception as e:
                frappe.log_error(
                    message=f"Buyer count update failed for level {level_name}: {str(e)}",
                    title="Buyer Level Count Error"
                )

    frappe.db.commit()

    frappe.logger().info("Buyer KPI template stats update complete.")


def _update_template_stats(template_name):
    """Update statistics for a single Buyer KPI Template.

    Recalculates usage_count from Buyer KPI Score Log records that
    reference this template, and updates average_score.

    Args:
        template_name: Buyer KPI Template name.
    """
    from frappe.utils import now_datetime

    # Count usage from Buyer KPI Score Log if it exists
    usage_count = 0
    average_score = 0

    if frappe.db.exists("DocType", "Buyer KPI Score Log"):
        usage_count = frappe.db.count(
            "Buyer KPI Score Log",
            {"template": template_name}
        )

        if usage_count > 0:
            avg_result = frappe.db.sql("""
                SELECT AVG(overall_score) as avg_score
                FROM `tabBuyer KPI Score Log`
                WHERE template = %s AND status = 'Finalized'
            """, template_name, as_dict=True)

            if avg_result and avg_result[0].avg_score:
                average_score = round(avg_result[0].avg_score, 2)

    frappe.db.set_value("Buyer KPI Template", template_name, {
        "usage_count": usage_count,
        "average_score": average_score,
        "last_evaluated_at": now_datetime(),
    }, update_modified=False)


def refresh_user_segments():
    """
    Hourly task to evaluate and refresh User Segment membership.

    Scheduled: Hourly (via hooks.py).

    Steps:
    1. Acquire Redis lock to prevent concurrent execution
    2. Get all active User Segments with auto_refresh enabled
    3. For each segment:
       - Evaluate segment rules against all candidates
       - Sync membership (add new, deactivate removed, reactivate returned)
       - Update segment statistics (member_count, last_refreshed, duration)
    4. Commit per 100 members (handled inside sync_segment_members)

    Uses per-segment try/except to ensure a single failure doesn't block others.
    """
    lock_key = "refresh_user_segments_lock"
    if frappe.cache().get_value(lock_key):
        frappe.log_error(
            "refresh_user_segments already running",
            "Scheduler Lock"
        )
        return

    frappe.cache().set_value(lock_key, 1, expires_in_sec=3600)
    try:
        _run_user_segment_refresh()
    finally:
        frappe.cache().delete_value(lock_key)


def _run_user_segment_refresh():
    """Internal function to evaluate and refresh all active User Segments."""
    if not frappe.db.exists("DocType", "User Segment"):
        return

    if not frappe.db.exists("DocType", "Segment Member"):
        return

    # Get all active segments with auto_refresh enabled
    segments = frappe.get_all(
        "User Segment",
        filters={
            "status": "Active",
            "auto_refresh": 1,
        },
        fields=["name", "segment_name", "target_type"],
        order_by="priority desc"
    )

    if not segments:
        frappe.logger().info("No active auto-refresh segments found")
        return

    frappe.logger().info(
        f"Starting user segment refresh for {len(segments)} segments..."
    )

    processed = 0
    errors = 0

    for segment in segments:
        try:
            _refresh_single_segment(segment)
            processed += 1

        except Exception as e:
            errors += 1
            frappe.log_error(
                message=f"Segment refresh failed for {segment.name} "
                        f"({segment.segment_name}): {str(e)}",
                title="User Segment Refresh Error"
            )

    frappe.db.commit()

    frappe.logger().info(
        f"User segment refresh complete. Processed: {processed}, Errors: {errors}"
    )


def _refresh_single_segment(segment):
    """Evaluate rules and sync membership for a single User Segment.

    Evaluates the segment's rule groups and conditions against all
    candidate members (buyers or sellers based on target_type),
    then synchronizes the Segment Member records accordingly.
    Updates segment statistics (member_count, last_refreshed, duration).

    Args:
        segment: Dict with name, segment_name, and target_type fields.
    """
    from frappe.utils import now_datetime, time_diff_in_seconds

    start_time = now_datetime()

    # Load the full segment document for evaluation
    segment_doc = frappe.get_doc("User Segment", segment.name)

    # Evaluate segment rules to get matching member IDs
    matching_ids = segment_doc.evaluate_segment()

    # Determine member_type from target_type
    member_type = segment_doc.target_type  # "Buyer" or "Seller"

    # Sync membership: add new, deactivate removed, reactivate returned
    from tradehub_core.tradehub_core.doctype.segment_member.segment_member import (
        sync_segment_members,
    )

    stats = sync_segment_members(
        segment=segment_doc.name,
        member_type=member_type,
        matching_ids=matching_ids,
        source="Rule",
    )

    end_time = now_datetime()
    duration = time_diff_in_seconds(end_time, start_time)

    # Update segment statistics using set_value to avoid triggering full validate
    active_count = frappe.db.count(
        "Segment Member",
        {"segment": segment_doc.name, "is_active": 1}
    )

    frappe.db.set_value("User Segment", segment_doc.name, {
        "member_count": active_count,
        "last_refreshed": end_time,
        "last_refresh_duration": round(duration, 2),
    }, update_modified=False)

    frappe.logger().info(
        f"Segment '{segment.segment_name}' refreshed: "
        f"{len(matching_ids)} matching, "
        f"added={stats['added']}, removed={stats['removed']}, "
        f"reactivated={stats['reactivated']}, "
        f"duration={round(duration, 2)}s"
    )
