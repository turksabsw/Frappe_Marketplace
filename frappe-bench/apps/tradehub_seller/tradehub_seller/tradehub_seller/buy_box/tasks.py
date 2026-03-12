# Copyright (c) 2026, Trade Hub and contributors
# For license information, please see license.txt

"""
Buy Box Scheduled Tasks for Trade Hub B2B Marketplace.

Provides scheduled batch recalculation of Buy Box scores across all products.
Processes entries in configurable batch sizes to avoid overloading the system.

Tasks:
- scheduled_batch_recalculate(): Daily batch recalculation of all Buy Box scores
"""

import frappe
from frappe import _
from frappe.utils import cint


def scheduled_batch_recalculate():
	"""
	Scheduled batch recalculation of Buy Box scores for all products.

	Fetches all distinct SKU Products with active Buy Box entries and
	processes them in configurable batch sizes. The batch_size is read
	from Buy Box Settings (recalculation_batch_size field), defaulting
	to 100 if not configured.

	Called by scheduler via hooks.py cron at 0 2 * * * (daily at 2:00 AM).
	"""
	frappe.logger().info("Starting scheduled Buy Box batch recalculation...")

	# Read batch size from Buy Box Settings
	try:
		settings = frappe.get_single("Buy Box Settings")
		batch_size = cint(settings.recalculation_batch_size) or 100
	except Exception:
		batch_size = 100

	# Get all distinct products with active entries
	products = frappe.get_all(
		"Buy Box Entry",
		filters={"status": "Active"},
		fields=["sku_product"],
		group_by="sku_product"
	)

	if not products:
		frappe.logger().info("No active Buy Box entries found for recalculation")
		return

	total_products = len(products)
	recalculated = 0
	errors = 0

	frappe.logger().info(
		f"Found {total_products} products to recalculate (batch_size={batch_size})"
	)

	from tradehub_seller.tradehub_seller.doctype.buy_box_entry.buy_box_entry import (
		recalculate_buy_box_for_product,
	)

	# Process in batches
	for batch_start in range(0, total_products, batch_size):
		batch = products[batch_start:batch_start + batch_size]
		batch_num = (batch_start // batch_size) + 1

		frappe.logger().info(
			f"Processing batch {batch_num} ({len(batch)} products)"
		)

		for product in batch:
			try:
				recalculate_buy_box_for_product(
					product.sku_product,
					triggered_by="Scheduled"
				)
				recalculated += 1
			except Exception:
				errors += 1
				frappe.log_error(
					title=_("Buy Box Batch Recalculation Error: {0}").format(
						product.sku_product
					),
					message=frappe.get_traceback()
				)

		# Commit after each batch to avoid long-running transactions
		frappe.db.commit()

	frappe.logger().info(
		f"Buy Box batch recalculation complete. "
		f"Recalculated: {recalculated}, Errors: {errors}, "
		f"Total: {total_products}"
	)
