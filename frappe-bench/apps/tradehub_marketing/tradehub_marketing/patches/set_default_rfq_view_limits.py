# Copyright (c) 2026, TradeHub Marketing and contributors
# For license information, please see license.txt

"""
Patch: Set Default RFQ View Limits

This patch sets the default max_rfq_views values for existing
subscription packages:
- Free: 3 views per month
- Starter: 15 views per month
- Professional: 50 views per month
- Enterprise: 0 (unlimited)
"""

import frappe


def execute():
	"""Set default RFQ view limits per subscription package."""
	# Schema reload for migration safety
	frappe.reload_doc("tradehub_marketing", "doctype", "subscription_package")

	if not frappe.db.exists("DocType", "Subscription Package"):
		frappe.log_error(
			"Subscription Package DocType does not exist. Please run bench migrate first.",
			"Set Default RFQ View Limits Patch",
		)
		return

	# Default RFQ view limits per package
	package_limits = {
		"Free": 3,
		"Starter": 15,
		"Professional": 50,
		"Enterprise": 0,  # unlimited
	}

	for package_name, max_rfq_views in package_limits.items():
		if frappe.db.exists("Subscription Package", package_name):
			frappe.db.set_value(
				"Subscription Package",
				package_name,
				"max_rfq_views",
				max_rfq_views,
				update_modified=False,
			)

	frappe.db.commit()
