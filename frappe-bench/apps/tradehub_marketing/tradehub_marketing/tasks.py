"""
Scheduled tasks for TradeHub Marketing module.

Tasks moved from the monolithic tr_tradehub app during decomposition:
- campaign_tasks: Daily campaign status updates (activate/deactivate based on dates)
- group_buy_tasks: Hourly group buy commitment tracking and status updates
- check_subscription_transitions: Daily subscription status transitions
- send_subscription_reminders: Daily subscription billing reminders
- check_grace_period_expiry: Daily grace period expiry checks
- auto_cancel_long_suspended: Weekly auto-cancel of long-suspended subscriptions
- generate_subscription_report: Monthly subscription metrics report
"""

import frappe
from frappe.utils import nowdate, now_datetime, getdate, add_days


def campaign_tasks():
    """
    Daily scheduled task for campaign management.

    This task:
    1. Activates campaigns that have reached their start date
    2. Deactivates campaigns that have passed their end date
    3. Updates campaign metrics (impressions, clicks, conversions)
    4. Sends expiry notifications for campaigns ending soon
    """
    frappe.logger("tradehub_marketing").info("Running daily campaign tasks")

    today = getdate(nowdate())

    # Activate campaigns scheduled to start today
    campaigns_to_activate = frappe.get_all(
        "Campaign",
        filters={
            "status": "Scheduled",
            "start_date": ["<=", today]
        },
        pluck="name"
    )

    for campaign_name in campaigns_to_activate:
        try:
            doc = frappe.get_doc("Campaign", campaign_name)
            doc.status = "Active"
            doc.save(ignore_permissions=True)
            frappe.logger("tradehub_marketing").info(f"Activated campaign: {campaign_name}")
        except Exception as e:
            frappe.logger("tradehub_marketing").error(
                f"Failed to activate campaign {campaign_name}: {str(e)}"
            )

    # Deactivate campaigns that have ended
    campaigns_to_deactivate = frappe.get_all(
        "Campaign",
        filters={
            "status": "Active",
            "end_date": ["<", today]
        },
        pluck="name"
    )

    for campaign_name in campaigns_to_deactivate:
        try:
            doc = frappe.get_doc("Campaign", campaign_name)
            doc.status = "Completed"
            doc.save(ignore_permissions=True)
            frappe.logger("tradehub_marketing").info(f"Deactivated campaign: {campaign_name}")
        except Exception as e:
            frappe.logger("tradehub_marketing").error(
                f"Failed to deactivate campaign {campaign_name}: {str(e)}"
            )

    # Notify about campaigns ending in 3 days
    expiring_soon = add_days(today, 3)
    campaigns_expiring = frappe.get_all(
        "Campaign",
        filters={
            "status": "Active",
            "end_date": expiring_soon
        },
        fields=["name", "campaign_name", "owner"]
    )

    for campaign in campaigns_expiring:
        try:
            frappe.sendmail(
                recipients=[campaign.owner],
                subject=f"Campaign '{campaign.campaign_name}' ending soon",
                message=f"Your campaign '{campaign.campaign_name}' will end on {expiring_soon}. "
                        f"Please review and take necessary action.",
                now=True
            )
            frappe.logger("tradehub_marketing").info(
                f"Sent expiry notification for campaign: {campaign.name}"
            )
        except Exception as e:
            frappe.logger("tradehub_marketing").error(
                f"Failed to send expiry notification for {campaign.name}: {str(e)}"
            )

    frappe.db.commit()
    frappe.logger("tradehub_marketing").info(
        f"Campaign tasks completed. Activated: {len(campaigns_to_activate)}, "
        f"Deactivated: {len(campaigns_to_deactivate)}"
    )


def group_buy_tasks():
    """
    Hourly scheduled task for Group Buy management.

    This task:
    1. Checks Group Buys that have reached their commitment threshold
    2. Marks successful Group Buys for fulfillment
    3. Cancels Group Buys that failed to reach threshold by deadline
    4. Processes refunds for cancelled Group Buy commitments
    """
    frappe.logger("tradehub_marketing").info("Running hourly group buy tasks")

    now = now_datetime()

    # Check Group Buys that have reached deadline
    expired_group_buys = frappe.get_all(
        "Group Buy",
        filters={
            "status": "Active",
            "deadline": ["<", now]
        },
        fields=["name", "minimum_quantity", "current_quantity", "product"]
    )

    for gb in expired_group_buys:
        try:
            doc = frappe.get_doc("Group Buy", gb.name)

            if doc.current_quantity >= doc.minimum_quantity:
                # Group Buy succeeded - move to fulfillment
                doc.status = "Successful"
                doc.save(ignore_permissions=True)
                frappe.logger("tradehub_marketing").info(
                    f"Group Buy {gb.name} succeeded with {doc.current_quantity} commitments"
                )

                # Notify all participants
                notify_group_buy_participants(doc.name, "success")

            else:
                # Group Buy failed - trigger refunds
                doc.status = "Failed"
                doc.save(ignore_permissions=True)
                frappe.logger("tradehub_marketing").info(
                    f"Group Buy {gb.name} failed - only {doc.current_quantity}/{doc.minimum_quantity}"
                )

                # Process refunds for all commitments
                process_group_buy_refunds(doc.name)

                # Notify all participants
                notify_group_buy_participants(doc.name, "failed")

        except Exception as e:
            frappe.logger("tradehub_marketing").error(
                f"Failed to process Group Buy {gb.name}: {str(e)}"
            )

    # Check active Group Buys that have reached their threshold
    threshold_reached = frappe.get_all(
        "Group Buy",
        filters={
            "status": "Active"
        },
        fields=["name", "minimum_quantity", "current_quantity", "auto_close_on_threshold"]
    )

    for gb in threshold_reached:
        if gb.current_quantity >= gb.minimum_quantity and gb.auto_close_on_threshold:
            try:
                doc = frappe.get_doc("Group Buy", gb.name)
                doc.status = "Successful"
                doc.save(ignore_permissions=True)
                frappe.logger("tradehub_marketing").info(
                    f"Group Buy {gb.name} auto-closed after reaching threshold"
                )
                notify_group_buy_participants(doc.name, "success")
            except Exception as e:
                frappe.logger("tradehub_marketing").error(
                    f"Failed to auto-close Group Buy {gb.name}: {str(e)}"
                )

    frappe.db.commit()
    frappe.logger("tradehub_marketing").info("Group buy tasks completed")


def notify_group_buy_participants(group_buy_name, status):
    """
    Send notifications to all participants of a Group Buy.

    Args:
        group_buy_name: Name of the Group Buy document
        status: Either 'success' or 'failed'
    """
    commitments = frappe.get_all(
        "Group Buy Commitment",
        filters={"group_buy": group_buy_name},
        fields=["buyer", "buyer_email", "quantity"]
    )

    group_buy = frappe.get_doc("Group Buy", group_buy_name)

    for commitment in commitments:
        if status == "success":
            subject = f"Group Buy '{group_buy.title}' - Successful!"
            message = (
                f"Great news! The Group Buy '{group_buy.title}' has reached its goal. "
                f"Your commitment for {commitment.quantity} units will be processed shortly."
            )
        else:
            subject = f"Group Buy '{group_buy.title}' - Did not reach goal"
            message = (
                f"Unfortunately, the Group Buy '{group_buy.title}' did not reach its minimum commitment. "
                f"Your payment of {commitment.quantity} units will be refunded within 3-5 business days."
            )

        try:
            frappe.sendmail(
                recipients=[commitment.buyer_email],
                subject=subject,
                message=message,
                now=True
            )
        except Exception as e:
            frappe.logger("tradehub_marketing").error(
                f"Failed to notify {commitment.buyer_email} about Group Buy {group_buy_name}: {str(e)}"
            )


def process_group_buy_refunds(group_buy_name):
    """
    Process refunds for all commitments in a failed Group Buy.

    Args:
        group_buy_name: Name of the Group Buy document
    """
    commitments = frappe.get_all(
        "Group Buy Commitment",
        filters={
            "group_buy": group_buy_name,
            "payment_status": "Paid"
        },
        pluck="name"
    )

    for commitment_name in commitments:
        try:
            commitment = frappe.get_doc("Group Buy Commitment", commitment_name)
            commitment.payment_status = "Refund Pending"
            commitment.save(ignore_permissions=True)

            # Create refund in Group Buy Payment
            frappe.get_doc({
                "doctype": "Group Buy Payment",
                "group_buy_commitment": commitment_name,
                "group_buy": group_buy_name,
                "payment_type": "Refund",
                "amount": commitment.total_amount,
                "status": "Pending"
            }).insert(ignore_permissions=True)

            frappe.logger("tradehub_marketing").info(
                f"Created refund for commitment {commitment_name}"
            )
        except Exception as e:
            frappe.logger("tradehub_marketing").error(
                f"Failed to process refund for commitment {commitment_name}: {str(e)}"
            )


def subscription_renewal_tasks():
    """
    Daily task for subscription renewal processing.

    This task:
    1. Identifies subscriptions due for renewal
    2. Processes automatic renewals
    3. Sends renewal reminders for manual renewals
    4. Expires subscriptions that failed to renew
    """
    frappe.logger("tradehub_marketing").info("Running subscription renewal tasks")

    today = getdate(nowdate())

    # Find subscriptions expiring in 7 days
    expiring_date = add_days(today, 7)
    expiring_subscriptions = frappe.get_all(
        "Subscription",
        filters={
            "status": "Active",
            "end_date": expiring_date,
            "auto_renew": 0
        },
        fields=["name", "subscriber", "subscriber_email", "subscription_package"]
    )

    for sub in expiring_subscriptions:
        try:
            frappe.sendmail(
                recipients=[sub.subscriber_email],
                subject=f"Subscription renewal reminder",
                message=f"Your subscription to {sub.subscription_package} will expire on {expiring_date}. "
                        f"Please renew to continue enjoying the benefits.",
                now=True
            )
            frappe.logger("tradehub_marketing").info(
                f"Sent renewal reminder for subscription: {sub.name}"
            )
        except Exception as e:
            frappe.logger("tradehub_marketing").error(
                f"Failed to send renewal reminder for {sub.name}: {str(e)}"
            )

    # Expire subscriptions past their end date
    expired_subscriptions = frappe.get_all(
        "Subscription",
        filters={
            "status": "Active",
            "end_date": ["<", today]
        },
        pluck="name"
    )

    for sub_name in expired_subscriptions:
        try:
            sub = frappe.get_doc("Subscription", sub_name)
            sub.status = "Expired"
            sub.save(ignore_permissions=True)
            frappe.logger("tradehub_marketing").info(f"Expired subscription: {sub_name}")
        except Exception as e:
            frappe.logger("tradehub_marketing").error(
                f"Failed to expire subscription {sub_name}: {str(e)}"
            )

    frappe.db.commit()
    frappe.logger("tradehub_marketing").info("Subscription renewal tasks completed")


def check_subscription_transitions():
    """
    Daily scheduled task to check and process subscription status transitions.

    Iterates over all non-terminal subscriptions and calls
    check_and_transition_status() on each one to handle automatic
    status changes (Active → Pending Payment → Grace Period → Suspended → Cancelled).
    """
    frappe.logger("tradehub_marketing").info("Running check_subscription_transitions task")

    subscriptions = frappe.get_all(
        "Subscription",
        filters={
            "status": ["in", ["Active", "Trial", "Pending Payment", "Grace Period", "Suspended"]]
        },
        pluck="name"
    )

    transitioned = 0
    for sub_name in subscriptions:
        try:
            sub = frappe.get_doc("Subscription", sub_name)
            result = sub.check_and_transition_status()
            if result.get("changed"):
                transitioned += 1
            frappe.db.commit()
        except Exception as e:
            frappe.db.rollback()
            frappe.log_error(
                message=f"Failed to check transition for subscription {sub_name}: {str(e)}",
                title="Subscription Transition Error"
            )

    frappe.logger("tradehub_marketing").info(
        f"check_subscription_transitions completed. "
        f"Checked: {len(subscriptions)}, Transitioned: {transitioned}"
    )


def send_subscription_reminders():
    """
    Daily scheduled task to send subscription billing reminders.

    Iterates over all subscriptions in reminder-eligible statuses and calls
    send_subscription_reminder() on each to send due/overdue notifications
    based on Subscription Billing Settings reminder_days configuration.
    """
    frappe.logger("tradehub_marketing").info("Running send_subscription_reminders task")

    subscriptions = frappe.get_all(
        "Subscription",
        filters={
            "status": ["in", ["Active", "Trial", "Pending Payment", "Grace Period"]]
        },
        pluck="name"
    )

    sent_count = 0
    for sub_name in subscriptions:
        try:
            sub = frappe.get_doc("Subscription", sub_name)
            reminders_sent = sub.send_subscription_reminder()
            if reminders_sent:
                sent_count += 1
            frappe.db.commit()
        except Exception as e:
            frappe.db.rollback()
            frappe.log_error(
                message=f"Failed to send reminders for subscription {sub_name}: {str(e)}",
                title="Subscription Reminder Error"
            )

    frappe.logger("tradehub_marketing").info(
        f"send_subscription_reminders completed. "
        f"Checked: {len(subscriptions)}, Reminders sent: {sent_count}"
    )


def check_grace_period_expiry():
    """
    Daily scheduled task to check for expired grace periods.

    Iterates over all subscriptions in Grace Period status and calls
    check_grace_period_expiry() on each to suspend subscriptions
    whose grace period has expired without payment.
    """
    frappe.logger("tradehub_marketing").info("Running check_grace_period_expiry task")

    subscriptions = frappe.get_all(
        "Subscription",
        filters={
            "status": "Grace Period"
        },
        pluck="name"
    )

    expired_count = 0
    for sub_name in subscriptions:
        try:
            sub = frappe.get_doc("Subscription", sub_name)
            if sub.check_grace_period_expiry():
                expired_count += 1
            frappe.db.commit()
        except Exception as e:
            frappe.db.rollback()
            frappe.log_error(
                message=f"Failed to check grace period for subscription {sub_name}: {str(e)}",
                title="Grace Period Expiry Error"
            )

    frappe.logger("tradehub_marketing").info(
        f"check_grace_period_expiry completed. "
        f"Checked: {len(subscriptions)}, Expired: {expired_count}"
    )


def auto_cancel_long_suspended():
    """
    Weekly scheduled task to auto-cancel subscriptions that have been
    suspended for longer than the configured auto_cancel_after_suspension_days.

    Reads the threshold from Subscription Billing Settings and cancels
    subscriptions that have exceeded it.
    """
    frappe.logger("tradehub_marketing").info("Running auto_cancel_long_suspended task")

    try:
        settings = frappe.get_cached_doc("Subscription Billing Settings")
        auto_cancel_days = settings.auto_cancel_after_suspension_days or 30
    except Exception:
        auto_cancel_days = 30

    cutoff_date = add_days(nowdate(), -auto_cancel_days)

    subscriptions = frappe.get_all(
        "Subscription",
        filters={
            "status": "Suspended",
            "suspended_at": ["<", cutoff_date]
        },
        pluck="name"
    )

    cancelled_count = 0
    for sub_name in subscriptions:
        try:
            sub = frappe.get_doc("Subscription", sub_name)
            sub.cancel_subscription(
                reason=f"Auto-cancelled after {auto_cancel_days} days of suspension"
            )
            cancelled_count += 1
            frappe.db.commit()
        except Exception as e:
            frappe.db.rollback()
            frappe.log_error(
                message=f"Failed to auto-cancel subscription {sub_name}: {str(e)}",
                title="Auto Cancel Subscription Error"
            )

    frappe.logger("tradehub_marketing").info(
        f"auto_cancel_long_suspended completed. "
        f"Checked: {len(subscriptions)}, Cancelled: {cancelled_count}"
    )


def generate_subscription_report():
    """
    Monthly scheduled task to generate subscription metrics report.

    Collects subscription statistics (active, trial, suspended, cancelled counts,
    revenue metrics, churn rate) and creates a log entry for monitoring.
    """
    frappe.logger("tradehub_marketing").info("Running generate_subscription_report task")

    try:
        today = getdate(nowdate())

        # Gather subscription metrics by status
        status_counts = {}
        for status in ["Active", "Trial", "Pending Payment", "Grace Period", "Suspended", "Cancelled", "Expired"]:
            count = frappe.db.count("Subscription", filters={"status": status})
            status_counts[status] = count

        total = sum(status_counts.values())

        # Calculate churn: cancelled + expired in the last 30 days
        thirty_days_ago = add_days(today, -30)
        churned = frappe.db.count("Subscription", filters={
            "status": ["in", ["Cancelled", "Expired"]],
            "modified": [">=", thirty_days_ago]
        })

        # New subscriptions in the last 30 days
        new_subscriptions = frappe.db.count("Subscription", filters={
            "creation": [">=", thirty_days_ago]
        })

        # Build report summary
        report = (
            f"Subscription Report - {today}\n"
            f"{'=' * 40}\n"
            f"Total Subscriptions: {total}\n"
            f"Active: {status_counts.get('Active', 0)}\n"
            f"Trial: {status_counts.get('Trial', 0)}\n"
            f"Pending Payment: {status_counts.get('Pending Payment', 0)}\n"
            f"Grace Period: {status_counts.get('Grace Period', 0)}\n"
            f"Suspended: {status_counts.get('Suspended', 0)}\n"
            f"Cancelled: {status_counts.get('Cancelled', 0)}\n"
            f"Expired: {status_counts.get('Expired', 0)}\n"
            f"{'=' * 40}\n"
            f"New (last 30 days): {new_subscriptions}\n"
            f"Churned (last 30 days): {churned}\n"
        )

        frappe.logger("tradehub_marketing").info(report)
        frappe.db.commit()

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(
            message=f"Failed to generate subscription report: {str(e)}",
            title="Subscription Report Error"
        )
