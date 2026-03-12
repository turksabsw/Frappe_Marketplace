# Copyright (c) 2026, Trade Hub and contributors
# For license information, please see license.txt

"""
Buy Box API Endpoints for Trade Hub B2B Marketplace.

Provides whitelisted API functions for Buy Box recalculation,
seller status querying, and product Buy Box information retrieval.

Endpoints:
- recalculate(sku_product): Trigger Buy Box recalculation for a product
- get_seller_status(seller, sku_product=None): Get seller's Buy Box status
- get_product_buy_box(sku_product): Get product Buy Box winner and entries
"""

import frappe
from frappe import _
from frappe.utils import flt, cint


@frappe.whitelist()
def recalculate(sku_product):
	"""
	Trigger Buy Box recalculation for a specific product.

	Validates the SKU Product exists, then delegates to the core
	recalculation engine in buy_box_entry.py via background queue.

	Args:
		sku_product: The SKU Product name

	Returns:
		dict: Recalculation result with success status and message
	"""
	if not sku_product:
		frappe.throw(_("SKU Product is required"))

	# Validate product exists
	if not frappe.db.exists("SKU Product", sku_product):
		frappe.throw(_("SKU Product {0} not found").format(sku_product))

	# Check if there are any entries for this product
	entry_count = frappe.db.count(
		"Buy Box Entry",
		filters={
			"sku_product": sku_product,
			"status": ("in", ["Active", "Inactive"]),
		}
	)

	if not entry_count:
		return {
			"success": False,
			"message": _("No Buy Box entries found for product {0}").format(sku_product)
		}

	# Delegate to the core recalculation function
	from tradehub_seller.tradehub_seller.doctype.buy_box_entry.buy_box_entry import (
		recalculate_buy_box_for_product,
	)

	try:
		result = recalculate_buy_box_for_product(sku_product, triggered_by="API")
		return result
	except Exception:
		frappe.log_error(
			title=_("Buy Box API Recalculation Error"),
			message=frappe.get_traceback()
		)
		return {
			"success": False,
			"message": _("Error during Buy Box recalculation for {0}").format(sku_product)
		}


@frappe.whitelist()
def get_seller_status(seller, sku_product=None):
	"""
	Get a seller's Buy Box status across products or for a specific product.

	Returns summary information including total entries, wins, average score,
	and win rate. If sku_product is provided, returns status for that specific
	product only.

	Args:
		seller: The Seller Profile name
		sku_product: Optional SKU Product filter

	Returns:
		dict: Seller Buy Box status with entries, wins, scores, and details
	"""
	if not seller:
		frappe.throw(_("Seller is required"))

	if not frappe.db.exists("Seller Profile", seller):
		frappe.throw(_("Seller Profile {0} not found").format(seller))

	filters = {
		"seller": seller,
		"status": ("in", ["Active", "Inactive"]),
	}

	if sku_product:
		filters["sku_product"] = sku_product

	entries = frappe.get_all(
		"Buy Box Entry",
		filters=filters,
		fields=[
			"name", "sku_product", "product_name", "offer_price", "currency",
			"delivery_days", "stock_available", "buy_box_score",
			"is_winner", "status", "rank", "total_competitors",
			"is_disqualified", "disqualification_reason",
			"improvement_suggestions", "last_score_update",
		],
		order_by="is_winner desc, buy_box_score desc"
	)

	if not entries:
		return {
			"seller": seller,
			"total_entries": 0,
			"active_entries": 0,
			"total_wins": 0,
			"win_rate": 0,
			"average_score": 0,
			"entries": []
		}

	active_entries = [e for e in entries if e.status == "Active"]
	total_wins = sum(1 for e in entries if e.is_winner)
	scores = [flt(e.buy_box_score) for e in active_entries if flt(e.buy_box_score) > 0]
	average_score = round(sum(scores) / len(scores), 2) if scores else 0
	win_rate = round((total_wins / len(active_entries)) * 100, 2) if active_entries else 0

	return {
		"seller": seller,
		"total_entries": len(entries),
		"active_entries": len(active_entries),
		"total_wins": total_wins,
		"win_rate": win_rate,
		"average_score": average_score,
		"entries": entries
	}


@frappe.whitelist()
def get_product_buy_box(sku_product):
	"""
	Get Buy Box information for a product including winner and all entries.

	Returns the current winner details and a ranked list of all active
	Buy Box entries for the product.

	Args:
		sku_product: The SKU Product name

	Returns:
		dict: Product Buy Box data with winner info and ranked entries
	"""
	if not sku_product:
		frappe.throw(_("SKU Product is required"))

	if not frappe.db.exists("SKU Product", sku_product):
		frappe.throw(_("SKU Product {0} not found").format(sku_product))

	# Get winner
	winner = frappe.get_all(
		"Buy Box Entry",
		filters={
			"sku_product": sku_product,
			"status": "Active",
			"is_winner": 1
		},
		fields=[
			"name", "seller", "seller_name", "offer_price", "currency",
			"delivery_days", "stock_available", "buy_box_score",
			"seller_average_rating", "seller_tier", "winner_since",
			"rank", "total_competitors",
		],
		limit=1
	)

	# Get all active entries ranked by score
	entries = frappe.get_all(
		"Buy Box Entry",
		filters={
			"sku_product": sku_product,
			"status": "Active",
		},
		fields=[
			"name", "seller", "seller_name", "offer_price", "currency",
			"delivery_days", "stock_available", "buy_box_score",
			"is_winner", "rank", "seller_average_rating",
			"price_score", "delivery_score", "rating_score",
			"stock_score", "service_score", "seller_tier_bonus",
			"is_disqualified",
		],
		order_by="buy_box_score desc"
	)

	return {
		"sku_product": sku_product,
		"has_winner": bool(winner),
		"winner": winner[0] if winner else None,
		"total_entries": len(entries),
		"entries": entries
	}


# =============================================================================
# DOC EVENT HANDLERS (called from hooks.py doc_events)
# =============================================================================


def on_buy_box_entry_update(doc, method):
	"""
	Hook handler for Buy Box Entry on_update event.

	Triggers recalculation for the product when a Buy Box Entry is updated.
	Uses Redis-based cooldown to prevent recalculation storms.

	Args:
		doc: The Buy Box Entry document
		method: The hook method name
	"""
	if not doc.sku_product:
		return

	# Check cooldown to prevent rapid recalculation
	cache_key = f"trade_hub:buybox_cooldown:{doc.sku_product}"
	cooldown_active = frappe.cache().get_value(cache_key)

	if cooldown_active:
		return

	# Set cooldown
	try:
		from tradehub_seller.tradehub_seller.buy_box.scoring import get_buy_box_settings
		settings = get_buy_box_settings()
		cooldown_seconds = cint(settings.cooldown_seconds) or 300
	except Exception:
		cooldown_seconds = 300

	frappe.cache().set_value(cache_key, 1, expires_in_sec=cooldown_seconds)

	# Enqueue recalculation
	frappe.enqueue(
		"tradehub_seller.tradehub_seller.doctype.buy_box_entry.buy_box_entry.recalculate_buy_box_for_product",
		sku_product=doc.sku_product,
		triggered_by="Hook",
		queue="short",
		deduplicate=True
	)


def on_seller_profile_update(doc, method):
	"""
	Hook handler for Seller Profile on_update event.

	Triggers Buy Box recalculation for all products where this seller
	has active entries, since seller status/metrics changes may affect
	scoring and disqualification.

	Args:
		doc: The Seller Profile document
		method: The hook method name
	"""
	# Get all products where this seller has active entries
	products = frappe.get_all(
		"Buy Box Entry",
		filters={
			"seller": doc.name,
			"status": "Active",
		},
		fields=["sku_product"],
		group_by="sku_product"
	)

	if not products:
		return

	for product in products:
		frappe.enqueue(
			"tradehub_seller.tradehub_seller.doctype.buy_box_entry.buy_box_entry.recalculate_buy_box_for_product",
			sku_product=product.sku_product,
			triggered_by="Hook",
			queue="short",
			deduplicate=True
		)
