# Copyright (c) 2026, TR TradeHub and contributors
# For license information, please see license.txt

"""
Wishlist Notification Template Seed Data

Creates 7 Notification Template records for wishlist-related events:
- WISH-PRICE-DROP-EMAIL: Price drop notification (Email)
- WISH-PRICE-DROP-SMS: Price drop notification (SMS)
- WISH-LOW-STOCK-EMAIL: Low stock alert (Email)
- WISH-LOW-STOCK-SMS: Low stock alert (SMS)
- WISH-BACK-IN-STOCK-EMAIL: Back in stock notification (Email)
- WISH-SHARE-INVITE-EMAIL: Wishlist share invitation (Email)
- WISH-DAILY-DIGEST-EMAIL: Daily wishlist digest (Email)

Usage:
    bench --site [site] execute tradehub_catalog.tradehub_catalog.wishlist.seed_templates.seed_wishlist_notification_templates
"""

import frappe
from frappe import _


# =============================================================================
# TEMPLATE DEFINITIONS
# =============================================================================

WISHLIST_TEMPLATES = [
	{
		"template_code": "WISH-PRICE-DROP-EMAIL",
		"template_name": "Wishlist Price Drop (Email)",
		"notification_channel": "Email",
		"event_type": "Price Change Alert",
		"priority": "Normal",
		"subject": "Price drop on {{ item_name }} in your wishlist",
		"body": """<div style="font-family: Arial, sans-serif; max-width: 600px;">
<h2>Price Drop Alert</h2>
<p>Good news! An item in your wishlist has dropped in price.</p>
<table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
<tr>
<td style="padding: 8px; border: 1px solid #ddd;"><strong>Item</strong></td>
<td style="padding: 8px; border: 1px solid #ddd;">{{ item_name }}</td>
</tr>
<tr>
<td style="padding: 8px; border: 1px solid #ddd;"><strong>Original Price</strong></td>
<td style="padding: 8px; border: 1px solid #ddd;">{{ added_price }}</td>
</tr>
<tr>
<td style="padding: 8px; border: 1px solid #ddd;"><strong>Current Price</strong></td>
<td style="padding: 8px; border: 1px solid #ddd;">{{ current_price }}</td>
</tr>
<tr>
<td style="padding: 8px; border: 1px solid #ddd;"><strong>Savings</strong></td>
<td style="padding: 8px; border: 1px solid #ddd;">{{ drop_amount }} ({{ pct }}% off)</td>
</tr>
</table>
<p>Don't miss out on this deal!</p>
</div>""",
		"plain_text_body": (
			"Price Drop Alert: {{ item_name }} has dropped from "
			"{{ added_price }} to {{ current_price }} ({{ pct }}% off). "
			"You save {{ drop_amount }}!"
		),
		"available_variables": '["item_name", "product", "added_price", "current_price", "pct", "drop_amount"]',
		"description": "Sent when a wishlist item's price drops by 5% or more.",
	},
	{
		"template_code": "WISH-PRICE-DROP-SMS",
		"template_name": "Wishlist Price Drop (SMS)",
		"notification_channel": "SMS",
		"event_type": "Price Change Alert",
		"priority": "Normal",
		"subject": "",
		"body": "{{ item_name }} price dropped {{ pct }}%! Now {{ current_price }} (was {{ added_price }}). Save {{ drop_amount }}.",
		"plain_text_body": "{{ item_name }} price dropped {{ pct }}%! Now {{ current_price }} (was {{ added_price }}).",
		"available_variables": '["item_name", "product", "added_price", "current_price", "pct", "drop_amount"]',
		"description": "SMS notification for wishlist price drops.",
	},
	{
		"template_code": "WISH-LOW-STOCK-EMAIL",
		"template_name": "Wishlist Low Stock Alert (Email)",
		"notification_channel": "Email",
		"event_type": "Low Stock Alert",
		"priority": "High",
		"subject": "{{ item_name }} is running low on stock",
		"body": """<div style="font-family: Arial, sans-serif; max-width: 600px;">
<h2>Low Stock Alert</h2>
<p>An item in your wishlist is running low on stock.</p>
<table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
<tr>
<td style="padding: 8px; border: 1px solid #ddd;"><strong>Item</strong></td>
<td style="padding: 8px; border: 1px solid #ddd;">{{ item_name }}</td>
</tr>
<tr>
<td style="padding: 8px; border: 1px solid #ddd;"><strong>Remaining Stock</strong></td>
<td style="padding: 8px; border: 1px solid #ddd;">{{ stock_qty }} units</td>
</tr>
</table>
<p>Order soon before it runs out!</p>
</div>""",
		"plain_text_body": (
			"Low Stock Alert: {{ item_name }} has only {{ stock_qty }} units left. "
			"Order soon before it runs out!"
		),
		"available_variables": '["item_name", "product", "stock_qty"]',
		"description": "Sent when a wishlist item's stock drops below the threshold.",
	},
	{
		"template_code": "WISH-LOW-STOCK-SMS",
		"template_name": "Wishlist Low Stock Alert (SMS)",
		"notification_channel": "SMS",
		"event_type": "Low Stock Alert",
		"priority": "High",
		"subject": "",
		"body": "Low stock: {{ item_name }} - only {{ stock_qty }} left. Order now!",
		"plain_text_body": "Low stock: {{ item_name }} - only {{ stock_qty }} left.",
		"available_variables": '["item_name", "product", "stock_qty"]',
		"description": "SMS notification for low stock wishlist items.",
	},
	{
		"template_code": "WISH-BACK-IN-STOCK-EMAIL",
		"template_name": "Wishlist Back In Stock (Email)",
		"notification_channel": "Email",
		"event_type": "Back In Stock",
		"priority": "Normal",
		"subject": "{{ item_name }} is back in stock!",
		"body": """<div style="font-family: Arial, sans-serif; max-width: 600px;">
<h2>Back In Stock!</h2>
<p>Great news! An item from your wishlist is available again.</p>
<table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
<tr>
<td style="padding: 8px; border: 1px solid #ddd;"><strong>Item</strong></td>
<td style="padding: 8px; border: 1px solid #ddd;">{{ item_name }}</td>
</tr>
</table>
<p>Grab it before it sells out again!</p>
</div>""",
		"plain_text_body": (
			"Back In Stock: {{ item_name }} is available again! "
			"Order now before it sells out."
		),
		"available_variables": '["item_name", "product"]',
		"description": "Sent when a previously out-of-stock wishlist item becomes available.",
	},
	{
		"template_code": "WISH-SHARE-INVITE-EMAIL",
		"template_name": "Wishlist Share Invitation (Email)",
		"notification_channel": "Email",
		"event_type": "Wishlist Share",
		"priority": "Normal",
		"subject": "{{ sender_name }} shared a wishlist with you",
		"body": """<div style="font-family: Arial, sans-serif; max-width: 600px;">
<h2>Wishlist Shared With You</h2>
<p>{{ sender_name }} has shared their wishlist <strong>{{ wishlist_name }}</strong> with you.</p>
<p>
<a href="{{ share_url }}" style="display: inline-block; padding: 12px 24px; background-color: #28A745; color: white; text-decoration: none; border-radius: 4px;">
View Wishlist
</a>
</p>
</div>""",
		"plain_text_body": (
			"{{ sender_name }} shared their wishlist '{{ wishlist_name }}' with you. "
			"View it here: {{ share_url }}"
		),
		"available_variables": '["sender_name", "wishlist_name", "share_url"]',
		"description": "Sent when a user shares their public wishlist with another user.",
	},
	{
		"template_code": "WISH-DAILY-DIGEST-EMAIL",
		"template_name": "Wishlist Daily Digest (Email)",
		"notification_channel": "Email",
		"event_type": "Wishlist Digest",
		"priority": "Low",
		"subject": "Your daily wishlist update",
		"body": """<div style="font-family: Arial, sans-serif; max-width: 600px;">
<h2>Your Daily Wishlist Update</h2>
<p>Here's a summary of price changes in your wishlist <strong>{{ wishlist_name }}</strong>:</p>
<table style="width: 100%; border-collapse: collapse; margin: 16px 0;">
<tr style="background-color: #f8f9fa;">
<th style="padding: 8px; border: 1px solid #ddd; text-align: left;">Item</th>
<th style="padding: 8px; border: 1px solid #ddd; text-align: right;">Was</th>
<th style="padding: 8px; border: 1px solid #ddd; text-align: right;">Now</th>
<th style="padding: 8px; border: 1px solid #ddd; text-align: right;">Change</th>
</tr>
{% for item in items %}
<tr>
<td style="padding: 8px; border: 1px solid #ddd;">{{ item.item_name }}</td>
<td style="padding: 8px; border: 1px solid #ddd; text-align: right;">{{ item.added_price }}</td>
<td style="padding: 8px; border: 1px solid #ddd; text-align: right;">{{ item.current_price }}</td>
<td style="padding: 8px; border: 1px solid #ddd; text-align: right;">-{{ item.drop_pct }}%</td>
</tr>
{% endfor %}
</table>
<p><strong>{{ item_count }}</strong> item(s) with price changes as of {{ date }}.</p>
</div>""",
		"plain_text_body": (
			"Your daily wishlist update for {{ wishlist_name }}: "
			"{{ item_count }} item(s) have price changes. "
			"Check your wishlist for details."
		),
		"available_variables": '["wishlist_name", "items", "item_count", "date"]',
		"description": "Daily digest email summarizing price changes for wishlist items.",
	},
]


# =============================================================================
# SEED FUNCTION
# =============================================================================


def seed_wishlist_notification_templates(tenant=None):
	"""
	Create wishlist notification templates if they don't already exist.

	This function is idempotent — it skips templates that already exist
	(matched by template_code).

	Args:
		tenant: Optional tenant name. If None, creates global templates.

	Returns:
		dict: Summary with 'created' and 'skipped' lists.
	"""
	created = []
	skipped = []

	for template_data in WISHLIST_TEMPLATES:
		template_code = template_data["template_code"]

		# Check if template already exists
		if frappe.db.exists("Notification Template", {"template_code": template_code}):
			skipped.append(template_code)
			continue

		try:
			doc = frappe.new_doc("Notification Template")
			doc.update(template_data)
			doc.enabled = 1
			doc.is_default = 1
			doc.retry_count = 3

			if tenant:
				doc.tenant = tenant
				doc.is_global = 0
			else:
				doc.is_global = 1

			doc.insert(ignore_permissions=True)
			created.append(template_code)

		except Exception as e:
			frappe.log_error(
				message=f"Failed to create notification template '{template_code}': {str(e)}",
				title="Wishlist Template Seed Error"
			)

	frappe.db.commit()

	summary = {
		"created": created,
		"skipped": skipped,
	}

	frappe.logger("tradehub_catalog").info(
		f"Wishlist notification template seed completed: "
		f"{len(created)} created, {len(skipped)} skipped"
	)

	if created:
		frappe.msgprint(
			_("Wishlist notification templates: {0} created, {1} already existed").format(
				len(created), len(skipped)
			)
		)

	return summary
