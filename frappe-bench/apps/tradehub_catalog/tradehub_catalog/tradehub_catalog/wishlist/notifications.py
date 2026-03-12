# Copyright (c) 2026, TR TradeHub and contributors
# For license information, please see license.txt

"""
Wishlist Notification Helpers

Functions for sending wishlist-related notifications via the
Notification Template DocType. Implements rate limiting to prevent
notification fatigue:

- Minimum 5% price drop before notification
- 24-hour per-product cooldown per user (Redis-based)
- Maximum 10 notifications per user per day (Redis-based)

Redis Key Patterns:
- Per-product cooldown: trade_hub:wish_notif:{user}:{product} (TTL=86400s)
- Daily user cap: trade_hub:wish_notif_daily:{user}:{date} (TTL=86400s)
"""

import frappe
from frappe import _
from frappe.utils import flt, cint, now_datetime, today, get_datetime
from typing import Dict, Any, Optional, List

# Rate limit constants
MIN_PRICE_DROP_PCT = 5.0  # Minimum 5% price drop before notification
PRODUCT_COOLDOWN_SECONDS = 86400  # 24 hours per-product cooldown
MAX_DAILY_NOTIFICATIONS = 10  # Maximum 10 notifications per user per day
DAILY_CAP_TTL_SECONDS = 86400  # Daily counter TTL (24 hours)

# Redis key prefixes
PRODUCT_COOLDOWN_PREFIX = "trade_hub:wish_notif"
DAILY_CAP_PREFIX = "trade_hub:wish_notif_daily"


def can_send_notification(user: str, product: str) -> bool:
    """
    Check if a notification can be sent to a user for a specific product.

    Enforces two rate limits:
    1. 24-hour cooldown per product per user
    2. 10 notifications per user per day

    Args:
        user: User email/ID
        product: Product document name

    Returns:
        True if notification can be sent, False if rate-limited
    """
    # Check per-product cooldown (24h)
    cooldown_key = f"{PRODUCT_COOLDOWN_PREFIX}:{user}:{product}"
    if frappe.cache().get_value(cooldown_key, expires=True):
        return False

    # Check daily cap (10/day)
    daily_key = f"{DAILY_CAP_PREFIX}:{user}:{today()}"
    daily_count = cint(frappe.cache().get_value(daily_key, expires=True))
    if daily_count >= MAX_DAILY_NOTIFICATIONS:
        return False

    return True


def record_notification_sent(user: str, product: str) -> None:
    """
    Record that a notification was sent to enforce rate limits.

    Sets the per-product cooldown and increments the daily counter.

    Args:
        user: User email/ID
        product: Product document name
    """
    # Set per-product cooldown (24h)
    cooldown_key = f"{PRODUCT_COOLDOWN_PREFIX}:{user}:{product}"
    frappe.cache().set_value(cooldown_key, 1, expires_in_sec=PRODUCT_COOLDOWN_SECONDS)

    # Increment daily counter
    daily_key = f"{DAILY_CAP_PREFIX}:{user}:{today()}"
    daily_count = cint(frappe.cache().get_value(daily_key, expires=True))
    frappe.cache().set_value(daily_key, daily_count + 1, expires_in_sec=DAILY_CAP_TTL_SECONDS)


def is_significant_price_drop(added_price: float, current_price: float) -> bool:
    """
    Check if a price drop meets the minimum threshold for notification.

    Requires at least a 5% drop from the added price.

    Args:
        added_price: Original price when item was added to wishlist
        current_price: Current price of the product

    Returns:
        True if the price drop is >= 5%
    """
    if flt(added_price) <= 0:
        return False

    if flt(current_price) >= flt(added_price):
        return False

    drop_pct = ((flt(added_price) - flt(current_price)) / flt(added_price)) * 100
    return drop_pct >= MIN_PRICE_DROP_PCT


def send_price_drop_notification(
    user: str,
    product: str,
    item_name: str,
    added_price: float,
    current_price: float,
    channel: str = "Email"
) -> bool:
    """
    Send a price drop notification if rate limits allow.

    Uses the Notification Template DocType to send notifications
    via the configured channel (Email or SMS).

    Args:
        user: User email/ID to notify
        product: Product document name
        item_name: Display name of the item
        added_price: Original price when added
        current_price: Current price
        channel: Notification channel (Email or SMS)

    Returns:
        True if notification was sent, False if skipped due to rate limits
    """
    # Check minimum price drop threshold
    if not is_significant_price_drop(added_price, current_price):
        return False

    # Check rate limits
    if not can_send_notification(user, product):
        return False

    drop_pct = round(((flt(added_price) - flt(current_price)) / flt(added_price)) * 100, 1)

    template_code = "WISH-PRICE-DROP-EMAIL" if channel == "Email" else "WISH-PRICE-DROP-SMS"

    try:
        _send_notification(
            template_code=template_code,
            user=user,
            context={
                "item_name": item_name,
                "product": product,
                "added_price": flt(added_price, 2),
                "current_price": flt(current_price, 2),
                "pct": drop_pct,
                "drop_amount": flt(flt(added_price) - flt(current_price), 2),
            }
        )

        # Record notification for rate limiting
        record_notification_sent(user, product)
        return True

    except Exception as e:
        frappe.log_error(
            f"Error sending price drop notification to {user} for {product}: {str(e)}",
            "Wishlist Notification Error"
        )
        return False


def send_low_stock_notification(
    user: str,
    product: str,
    item_name: str,
    stock_qty: int,
    channel: str = "Email"
) -> bool:
    """
    Send a low stock notification for a wishlist item.

    Args:
        user: User email/ID to notify
        product: Product document name
        item_name: Display name of the item
        stock_qty: Current stock quantity
        channel: Notification channel (Email or SMS)

    Returns:
        True if notification was sent, False if rate-limited
    """
    if not can_send_notification(user, product):
        return False

    template_code = "WISH-LOW-STOCK-EMAIL" if channel == "Email" else "WISH-LOW-STOCK-SMS"

    try:
        _send_notification(
            template_code=template_code,
            user=user,
            context={
                "item_name": item_name,
                "product": product,
                "stock_qty": stock_qty,
            }
        )

        record_notification_sent(user, product)
        return True

    except Exception as e:
        frappe.log_error(
            f"Error sending low stock notification to {user} for {product}: {str(e)}",
            "Wishlist Notification Error"
        )
        return False


def send_back_in_stock_notification(
    user: str,
    product: str,
    item_name: str,
    channel: str = "Email"
) -> bool:
    """
    Send a back-in-stock notification for a wishlist item.

    Args:
        user: User email/ID to notify
        product: Product document name
        item_name: Display name of the item
        channel: Notification channel (Email or SMS)

    Returns:
        True if notification was sent, False if rate-limited
    """
    if not can_send_notification(user, product):
        return False

    template_code = "WISH-BACK-IN-STOCK-EMAIL"

    try:
        _send_notification(
            template_code=template_code,
            user=user,
            context={
                "item_name": item_name,
                "product": product,
            }
        )

        record_notification_sent(user, product)
        return True

    except Exception as e:
        frappe.log_error(
            f"Error sending back in stock notification to {user} for {product}: {str(e)}",
            "Wishlist Notification Error"
        )
        return False


def send_wishlist_share_notification(
    recipient_email: str,
    sender_name: str,
    wishlist_name: str,
    share_url: str
) -> bool:
    """
    Send a wishlist share invitation notification.

    This notification is not subject to per-product rate limits,
    but respects the daily user cap.

    Args:
        recipient_email: Email address of the recipient
        sender_name: Display name of the sender
        wishlist_name: Name of the shared wishlist
        share_url: Public URL for the shared wishlist

    Returns:
        True if notification was sent, False otherwise
    """
    # Check daily cap only (no per-product cooldown for shares)
    daily_key = f"{DAILY_CAP_PREFIX}:{recipient_email}:{today()}"
    daily_count = cint(frappe.cache().get_value(daily_key, expires=True))
    if daily_count >= MAX_DAILY_NOTIFICATIONS:
        return False

    try:
        _send_notification(
            template_code="WISH-SHARE-INVITE-EMAIL",
            user=recipient_email,
            context={
                "sender_name": sender_name,
                "wishlist_name": wishlist_name,
                "share_url": share_url,
            }
        )

        # Increment daily counter
        frappe.cache().set_value(daily_key, daily_count + 1, expires_in_sec=DAILY_CAP_TTL_SECONDS)
        return True

    except Exception as e:
        frappe.log_error(
            f"Error sending wishlist share notification to {recipient_email}: {str(e)}",
            "Wishlist Notification Error"
        )
        return False


def send_daily_digest(
    user: str,
    wishlist_name: str,
    items_with_changes: List[Dict]
) -> bool:
    """
    Send a daily digest email with price changes for wishlist items.

    Args:
        user: User email/ID
        wishlist_name: Name of the wishlist
        items_with_changes: List of dicts with item details and price changes

    Returns:
        True if digest was sent, False otherwise
    """
    if not items_with_changes:
        return False

    # Check daily cap
    daily_key = f"{DAILY_CAP_PREFIX}:{user}:{today()}"
    daily_count = cint(frappe.cache().get_value(daily_key, expires=True))
    if daily_count >= MAX_DAILY_NOTIFICATIONS:
        return False

    try:
        _send_notification(
            template_code="WISH-DAILY-DIGEST-EMAIL",
            user=user,
            context={
                "wishlist_name": wishlist_name,
                "items": items_with_changes,
                "item_count": len(items_with_changes),
                "date": today(),
            }
        )

        # Increment daily counter
        frappe.cache().set_value(daily_key, daily_count + 1, expires_in_sec=DAILY_CAP_TTL_SECONDS)
        return True

    except Exception as e:
        frappe.log_error(
            f"Error sending daily digest to {user}: {str(e)}",
            "Wishlist Notification Error"
        )
        return False


def get_notification_stats(user: str) -> Dict:
    """
    Get notification rate limit stats for a user.

    Useful for UI display and debugging.

    Args:
        user: User email/ID

    Returns:
        Dict with daily_sent, daily_remaining, daily_limit
    """
    daily_key = f"{DAILY_CAP_PREFIX}:{user}:{today()}"
    daily_count = cint(frappe.cache().get_value(daily_key, expires=True))

    return {
        "daily_sent": daily_count,
        "daily_remaining": max(0, MAX_DAILY_NOTIFICATIONS - daily_count),
        "daily_limit": MAX_DAILY_NOTIFICATIONS,
        "min_price_drop_pct": MIN_PRICE_DROP_PCT,
        "product_cooldown_hours": PRODUCT_COOLDOWN_SECONDS // 3600,
    }


# =============================================================================
# INTERNAL HELPERS
# =============================================================================


def _send_notification(template_code: str, user: str, context: Dict) -> None:
    """
    Send a notification using a Notification Template.

    Looks up the template by its template_code, renders it with
    the provided context, and sends via the template's configured channel.

    Args:
        template_code: Notification Template code (e.g., WISH-PRICE-DROP-EMAIL)
        user: Recipient user email/ID
        context: Template variables for rendering

    Raises:
        frappe.exceptions.DoesNotExistError: If template not found
    """
    template = frappe.db.get_value(
        "Notification Template",
        {"template_code": template_code, "enabled": 1},
        ["name", "subject", "message", "channel"],
        as_dict=True
    )

    if not template:
        frappe.log_error(
            f"Notification template '{template_code}' not found or disabled",
            "Wishlist Notification Error"
        )
        return

    # Render subject and message with context
    rendered_subject = frappe.render_template(template.subject or "", context)
    rendered_message = frappe.render_template(template.message or "", context)

    channel = template.get("channel", "Email")

    if channel == "Email":
        frappe.sendmail(
            recipients=[user],
            subject=rendered_subject,
            message=rendered_message,
            reference_doctype="Notification Template",
            reference_name=template.name,
            now=False,
        )
    elif channel == "SMS":
        # SMS sending via Frappe's SMS Manager
        try:
            from frappe.core.doctype.sms_settings.sms_settings import send_sms
            phone = frappe.db.get_value("User", user, "mobile_no")
            if phone:
                send_sms([phone], rendered_message)
        except ImportError:
            frappe.log_error(
                f"SMS sending not available for template {template_code}",
                "Wishlist Notification Error"
            )
