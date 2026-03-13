"""
Scheduled tasks for TradeHub Commerce

This module contains scheduled tasks for the commerce layer.
Tasks are registered in hooks.py scheduler_events configuration.

Tasks:
- seller_payout: Daily task to process pending seller payouts
"""

import frappe
from frappe.utils import nowdate, add_days, getdate


def seller_payout():
    """
    Daily scheduled task to process pending seller payouts.

    This task:
    1. Finds all orders that have been delivered and payment received
    2. Calculates commission based on Commission Plan/Rules
    3. Creates payout entries for sellers
    4. Updates seller balance records
    5. Triggers payment gateway transfer for eligible payouts

    Business Rules:
    - Orders must be delivered for at least 7 days (return period)
    - All disputes/moderation cases must be resolved
    - Seller must have verified bank account
    - Minimum payout threshold must be met
    """
    frappe.logger().info("Running seller_payout scheduled task")

    try:
        # Get orders eligible for payout
        eligible_orders = get_payout_eligible_orders()

        for order in eligible_orders:
            try:
                process_order_payout(order)
            except Exception as e:
                frappe.log_error(
                    message=f"Failed to process payout for order {order.name}: {str(e)}",
                    title="Seller Payout Error"
                )
                continue

        # Process pending payouts that meet threshold
        process_pending_payouts()

        frappe.logger().info(f"Completed seller_payout: processed {len(eligible_orders)} orders")

    except Exception as e:
        frappe.log_error(
            message=str(e),
            title="Seller Payout Task Failed"
        )


def get_payout_eligible_orders():
    """
    Get orders that are eligible for seller payout.

    Criteria:
    - Order status is 'Delivered'
    - Delivery date is at least 7 days ago (return period)
    - Payment has been received
    - No open disputes or moderation cases
    - Payout not already processed
    """
    cutoff_date = add_days(nowdate(), -7)

    # In real implementation, this would query the Order DocType
    # For now, return empty list as DocTypes will be created in subtask-5-2
    return []


def process_order_payout(order):
    """
    Process payout for a single order.

    Steps:
    1. Calculate seller amount after commission deduction
    2. Create/update Seller Balance record
    3. Mark order as payout processed
    """
    # Get commission plan for seller
    commission = calculate_commission(order)

    # Calculate seller payout amount
    seller_amount = order.get("grand_total", 0) - commission

    # Update seller balance
    update_seller_balance(
        seller=order.get("seller"),
        amount=seller_amount,
        reference_doctype="Order",
        reference_name=order.get("name")
    )

    # Mark order as payout processed
    frappe.db.set_value("Order", order.get("name"), "payout_processed", 1)


def calculate_commission(order):
    """
    Calculate commission for an order based on Commission Plan/Rules.

    Commission calculation considers:
    - Base commission rate from Commission Plan
    - Category-specific rules
    - Seller tier discounts
    - Promotional adjustments
    """
    base_commission_rate = 0.10  # Default 10%

    # In real implementation, this would fetch from Commission Plan/Rule
    # based on seller's tier and product category

    return order.get("grand_total", 0) * base_commission_rate


def update_seller_balance(seller, amount, reference_doctype, reference_name):
    """
    Update seller balance with new payout amount.

    Creates or updates Seller Balance record and logs the transaction.
    """
    if not seller:
        return

    # In real implementation, this would update Seller Balance DocType
    # and create transaction log
    pass


def process_pending_payouts():
    """
    Process pending payouts that meet the minimum threshold.

    Business Rules:
    - Minimum payout threshold: 100 TRY
    - Seller must have verified bank account
    - Triggers payment gateway transfer
    """
    minimum_threshold = 100.0

    # In real implementation, this would:
    # 1. Query Seller Balance records >= threshold
    # 2. Verify seller bank account
    # 3. Create payout transfer via payment gateway
    # 4. Update Seller Balance and create Escrow Event
    pass


def process_escrow_release():
    """
    Release funds from escrow for completed orders.

    This is called as part of the payout process to move funds
    from escrow to seller balance.
    """
    # In real implementation, this would:
    # 1. Query Escrow Account for releasable funds
    # 2. Create Escrow Event records
    # 3. Update Escrow Account balance
    pass


# ==================== PPR Scheduled Tasks ====================


def check_ppr_closing_dates():
    """
    Daily task to check Platform Purchase Request closing dates.

    Finds PPRs whose closing_date has passed and transitions them
    from Published/Receiving Offers to Evaluation status.
    Also sends notifications to the PPR creator.
    """
    frappe.logger().info("Running check_ppr_closing_dates scheduled task")

    try:
        today = nowdate()

        # Find PPRs with passed closing dates still in open statuses
        expired_pprs = frappe.get_all(
            "Platform Purchase Request",
            filters={
                "status": ["in", ["Published", "Receiving Offers"]],
                "closing_date": ["<", today],
            },
            fields=["name", "title", "status", "closing_date", "created_by_user"],
        )

        for ppr in expired_pprs:
            try:
                doc = frappe.get_doc("Platform Purchase Request", ppr.name)
                doc.status = "Evaluation"
                doc.save()
                frappe.logger().info(
                    f"PPR {ppr.name} ({ppr.title}) moved to Evaluation - "
                    f"closing date {ppr.closing_date} has passed"
                )
            except Exception as e:
                frappe.log_error(
                    message=f"Failed to update PPR {ppr.name}: {str(e)}",
                    title="PPR Closing Date Check Error"
                )
                continue

        frappe.db.commit()
        frappe.logger().info(
            f"Completed check_ppr_closing_dates: processed {len(expired_pprs)} PPRs"
        )

    except Exception as e:
        frappe.log_error(
            message=str(e),
            title="PPR Closing Date Check Task Failed"
        )


def recalculate_ppr_scores():
    """
    Daily task to recalculate auto-scores for Seller Offers.

    Recalculates the composite auto_score for all submitted offers
    on active PPRs based on price, delivery, rating, and payment scores.
    """
    frappe.logger().info("Running recalculate_ppr_scores scheduled task")

    try:
        # Get PPRs that are actively receiving or evaluating offers
        active_pprs = frappe.get_all(
            "Platform Purchase Request",
            filters={
                "status": ["in", ["Receiving Offers", "Evaluation"]],
            },
            pluck="name",
        )

        recalculated_count = 0

        for ppr_name in active_pprs:
            try:
                offers = frappe.get_all(
                    "Seller Offer",
                    filters={
                        "purchase_request": ppr_name,
                        "status": ["in", ["Submitted", "Under Review"]],
                    },
                    pluck="name",
                )

                for offer_name in offers:
                    try:
                        _recalculate_offer_score(offer_name, ppr_name)
                        recalculated_count += 1
                    except Exception as e:
                        frappe.log_error(
                            message=f"Failed to recalculate score for offer {offer_name}: {str(e)}",
                            title="PPR Score Recalculation Error"
                        )
                        continue

            except Exception as e:
                frappe.log_error(
                    message=f"Failed to process PPR {ppr_name}: {str(e)}",
                    title="PPR Score Recalculation Error"
                )
                continue

        frappe.db.commit()
        frappe.logger().info(
            f"Completed recalculate_ppr_scores: recalculated {recalculated_count} offers"
        )

    except Exception as e:
        frappe.log_error(
            message=str(e),
            title="PPR Score Recalculation Task Failed"
        )


def _recalculate_offer_score(offer_name, ppr_name):
    """
    Recalculate auto_score for a single Seller Offer.

    Score components (each 0-25, total 0-100):
    - price_score: Based on competitiveness vs other offers
    - delivery_score: Based on proposed delivery vs target date
    - rating_score: Based on seller rating snapshot
    - payment_score: Based on payment terms favorability

    Args:
        offer_name: Seller Offer document name.
        ppr_name: Platform Purchase Request document name.
    """
    from frappe.utils import flt

    offer = frappe.get_doc("Seller Offer", offer_name)
    ppr = frappe.get_doc("Platform Purchase Request", ppr_name)

    # Price score: lower total = higher score (0-25)
    all_offer_amounts = frappe.get_all(
        "Seller Offer",
        filters={
            "purchase_request": ppr_name,
            "status": ["in", ["Submitted", "Under Review"]],
        },
        pluck="total_offered_amount",
    )

    price_score = 0
    if all_offer_amounts:
        min_amount = min(flt(a) for a in all_offer_amounts if flt(a) > 0) or 1
        max_amount = max(flt(a) for a in all_offer_amounts) or 1
        if max_amount > min_amount and flt(offer.total_offered_amount) > 0:
            price_score = 25 * (1 - (flt(offer.total_offered_amount) - min_amount) / (max_amount - min_amount))
        elif flt(offer.total_offered_amount) > 0:
            price_score = 25  # Only offer or all same price

    # Delivery score: closer to target = higher score (0-25)
    delivery_score = 0
    if offer.proposed_delivery_date and ppr.target_delivery_date:
        days_diff = (getdate(offer.proposed_delivery_date) - getdate(ppr.target_delivery_date)).days
        if days_diff <= 0:
            delivery_score = 25  # On or before target
        elif days_diff <= 30:
            delivery_score = 25 * (1 - days_diff / 30)

    # Rating score: higher rating = higher score (0-25)
    rating_score = flt(offer.seller_rating_snapshot, 2) * 5  # 0-5 scale * 5 = 0-25

    # Payment score: simple heuristic based on payment terms (0-25)
    payment_score = 12.5  # Default middle score
    if offer.proposed_payment_terms:
        terms_lower = (offer.proposed_payment_terms or "").lower()
        if "advance" in terms_lower or "prepaid" in terms_lower:
            payment_score = 25
        elif "delivery" in terms_lower or "cod" in terms_lower:
            payment_score = 20
        elif "net 30" in terms_lower or "30 days" in terms_lower:
            payment_score = 15
        elif "net 60" in terms_lower or "60 days" in terms_lower:
            payment_score = 10

    auto_score = flt(price_score + delivery_score + rating_score + payment_score, 2)

    frappe.db.set_value("Seller Offer", offer_name, {
        "auto_score": auto_score,
        "price_score": flt(price_score, 2),
        "delivery_score": flt(delivery_score, 2),
        "rating_score": flt(rating_score, 2),
        "payment_score": flt(payment_score, 2),
    }, update_modified=False)


def check_offer_validity():
    """
    Daily task to check Seller Offer validity periods.

    Finds offers whose validity_days have expired and marks them
    as expired or sends notifications to the seller.
    """
    frappe.logger().info("Running check_offer_validity scheduled task")

    try:
        today = getdate(nowdate())

        # Find submitted offers that may have expired
        active_offers = frappe.get_all(
            "Seller Offer",
            filters={
                "status": ["in", ["Submitted", "Under Review"]],
                "validity_days": [">", 0],
            },
            fields=["name", "creation", "validity_days", "seller"],
        )

        expired_count = 0
        for offer in active_offers:
            expiry_date = getdate(add_days(offer.creation, offer.validity_days))
            if expiry_date < today:
                try:
                    frappe.db.set_value(
                        "Seller Offer", offer.name, "status", "Withdrawn"
                    )
                    expired_count += 1
                    frappe.logger().info(
                        f"Offer {offer.name} expired (validity {offer.validity_days} days)"
                    )
                except Exception as e:
                    frappe.log_error(
                        message=f"Failed to expire offer {offer.name}: {str(e)}",
                        title="Offer Validity Check Error"
                    )
                    continue

        frappe.db.commit()
        frappe.logger().info(
            f"Completed check_offer_validity: expired {expired_count} offers"
        )

    except Exception as e:
        frappe.log_error(
            message=str(e),
            title="Offer Validity Check Task Failed"
        )


def create_recurring_purchase_requests():
    """
    Monthly task to create new Platform Purchase Requests from recurring templates.

    Finds PPRs marked as recurring and creates new copies for the next period.
    The new PPRs are created in Draft status for review before publishing.
    """
    frappe.logger().info("Running create_recurring_purchase_requests scheduled task")

    try:
        # Find closed/completed recurring PPRs that need renewal
        # Note: recurring fields will be added to PPR DocType when the feature is implemented
        recurring_pprs = frappe.get_all(
            "Platform Purchase Request",
            filters={
                "status": ["in", ["Closed", "Awarded"]],
                "is_recurring": 1,
            },
            fields=["name", "title", "description", "category", "target_type",
                     "budget_range_min", "budget_range_max", "currency",
                     "payment_terms", "minimum_seller_rating",
                     "require_sample", "allow_partial_offers",
                     "created_by_user", "tenant", "tenant_name"],
        ) if frappe.db.has_column("Platform Purchase Request", "is_recurring") else []

        created_count = 0
        for ppr in recurring_pprs:
            try:
                new_ppr = frappe.get_doc({
                    "doctype": "Platform Purchase Request",
                    "title": ppr.title,
                    "description": ppr.description,
                    "category": ppr.category,
                    "target_type": ppr.target_type,
                    "budget_range_min": ppr.budget_range_min,
                    "budget_range_max": ppr.budget_range_max,
                    "currency": ppr.currency,
                    "payment_terms": ppr.payment_terms,
                    "minimum_seller_rating": ppr.minimum_seller_rating,
                    "require_sample": ppr.require_sample,
                    "allow_partial_offers": ppr.allow_partial_offers,
                    "created_by_user": ppr.created_by_user,
                    "status": "Draft",
                })
                new_ppr.insert()
                created_count += 1
                frappe.logger().info(
                    f"Created recurring PPR {new_ppr.name} from template {ppr.name}"
                )
            except Exception as e:
                frappe.log_error(
                    message=f"Failed to create recurring PPR from {ppr.name}: {str(e)}",
                    title="Recurring PPR Creation Error"
                )
                continue

        frappe.db.commit()
        frappe.logger().info(
            f"Completed create_recurring_purchase_requests: created {created_count} PPRs"
        )

    except Exception as e:
        frappe.log_error(
            message=str(e),
            title="Recurring PPR Creation Task Failed"
        )
