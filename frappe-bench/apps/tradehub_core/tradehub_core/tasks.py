# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

"""
TradeHub Core Scheduled Tasks.

This module contains scheduled task functions for buyer-side operations:
- calculate_customer_grades: Weekly task to calculate buyer grades (A-F)

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
