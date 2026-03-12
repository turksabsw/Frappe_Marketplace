# Copyright (c) 2026, TR TradeHub and contributors
# For license information, please see license.txt

"""
Wishlist Scheduled Tasks

Background jobs for wishlist price tracking, availability monitoring,
social proof counter reconciliation, digest notifications, and orphan cleanup.

Schedule:
- update_wishlist_item_prices: Hourly
- check_wishlist_item_availability: Every 6 hours (cron 0 */6 * * *)
- reconcile_social_proof_counters: Daily at 03:00 (cron 0 3 * * *)
- send_price_drop_digest: Daily at 09:00 (cron 0 9 * * *)
- cleanup_orphaned_favorites: Weekly

Doc Event Handlers:
- on_wishlist_update: Recount product/listing wishlist_count on User Wishlist change
- on_wishlist_trash: Decrement product/listing wishlist_count on User Wishlist deletion
- on_favorite_insert: Log Quick Favorite creation (counter handled in controller)
- on_favorite_trash: Log Quick Favorite deletion (counter handled in controller)
"""

import frappe
from frappe import _
from frappe.utils import flt, cint, now_datetime, today, getdate, add_days


# =============================================================================
# SCHEDULED TASKS
# =============================================================================


def update_wishlist_item_prices():
	"""
	Hourly scheduled task to update current_price and price_change_pct
	for all active Wishlist Items.

	This task:
	1. Finds all User Wishlists with items
	2. For each Wishlist Item, fetches the current price from the linked Listing
	3. Calculates price_change_pct relative to added_price
	4. Updates the Wishlist Item record

	Business Rules:
	- Process max 500 items per run to avoid timeout
	- Only update items where listing is still active
	- Skip items without a valid listing reference
	"""
	frappe.logger("tradehub_catalog").info("Running update_wishlist_item_prices scheduled task")

	try:
		# Get all wishlist items with their current price data
		items = frappe.db.sql("""
			SELECT
				wi.name AS item_name,
				wi.parent AS wishlist_name,
				wi.listing,
				wi.product,
				wi.added_price,
				wi.current_price AS old_current_price,
				l.price AS listing_price
			FROM `tabWishlist Item` wi
			JOIN `tabUser Wishlist` uw ON uw.name = wi.parent
			LEFT JOIN `tabListing` l ON l.name = wi.listing AND l.status = 'Active'
			WHERE wi.listing IS NOT NULL AND wi.listing != ''
			ORDER BY wi.modified ASC
			LIMIT 500
		""", as_dict=True)

		updated_count = 0
		error_count = 0

		for item in items:
			try:
				_update_item_price(item)
				updated_count += 1
			except Exception as e:
				error_count += 1
				frappe.log_error(
					message=f"Failed to update price for wishlist item {item.item_name}: {str(e)}",
					title="Wishlist Price Update Error"
				)

		frappe.db.commit()

		frappe.logger("tradehub_catalog").info(
			f"Wishlist price update completed: {updated_count} updated, {error_count} errors"
		)

	except Exception as e:
		frappe.log_error(
			message=str(e),
			title="Wishlist Price Update Task Failed"
		)


def check_wishlist_item_availability():
	"""
	Every 6 hours: Check product/listing availability status for wishlist items.

	This task:
	1. Finds wishlist items linked to products or listings
	2. Checks if the product/listing is still active and in stock
	3. Sends back-in-stock notifications when previously unavailable items
	   become available again
	4. Sends low-stock notifications when stock drops below threshold

	Business Rules:
	- Process max 500 items per run
	- Low stock threshold: 5 units
	- Only notify users with notification_enabled=1
	"""
	frappe.logger("tradehub_catalog").info(
		"Running check_wishlist_item_availability scheduled task"
	)

	LOW_STOCK_THRESHOLD = 5

	try:
		# Get wishlist items with notification enabled
		items = frappe.db.sql("""
			SELECT
				wi.name AS item_name,
				wi.parent AS wishlist_name,
				wi.listing,
				wi.product,
				wi.notification_enabled,
				uw.user,
				l.status AS listing_status,
				l.stock_quantity,
				p.product_name
			FROM `tabWishlist Item` wi
			JOIN `tabUser Wishlist` uw ON uw.name = wi.parent
			LEFT JOIN `tabListing` l ON l.name = wi.listing
			LEFT JOIN `tabProduct` p ON p.name = wi.product
			WHERE wi.notification_enabled = 1
			ORDER BY wi.modified ASC
			LIMIT 500
		""", as_dict=True)

		notified_count = 0
		error_count = 0

		for item in items:
			try:
				if not item.listing:
					continue

				stock_qty = cint(item.stock_quantity)
				item_name = item.product_name or item.product or ""

				# Check for back-in-stock scenario
				if item.listing_status == "Active" and stock_qty > 0:
					# Check if this was previously out of stock via cache
					oos_key = f"trade_hub:wish_oos:{item.user}:{item.product}"
					was_oos = frappe.cache().get_value(oos_key, expires=True)

					if was_oos:
						from tradehub_catalog.tradehub_catalog.wishlist.notifications import (
							send_back_in_stock_notification,
						)
						send_back_in_stock_notification(
							user=item.user,
							product=item.product,
							item_name=item_name,
						)
						frappe.cache().delete_value(oos_key)
						notified_count += 1

				# Check for low stock
				elif item.listing_status == "Active" and 0 < stock_qty <= LOW_STOCK_THRESHOLD:
					from tradehub_catalog.tradehub_catalog.wishlist.notifications import (
						send_low_stock_notification,
					)
					send_low_stock_notification(
						user=item.user,
						product=item.product,
						item_name=item_name,
						stock_qty=stock_qty,
					)
					notified_count += 1

				# Mark as out of stock for future back-in-stock notification
				elif stock_qty <= 0:
					oos_key = f"trade_hub:wish_oos:{item.user}:{item.product}"
					frappe.cache().set_value(
						oos_key, 1, expires_in_sec=7 * 86400
					)

			except Exception as e:
				error_count += 1
				frappe.log_error(
					message=f"Failed to check availability for item {item.item_name}: {str(e)}",
					title="Wishlist Availability Check Error"
				)

		frappe.db.commit()

		frappe.logger("tradehub_catalog").info(
			f"Wishlist availability check completed: {notified_count} notifications, "
			f"{error_count} errors"
		)

	except Exception as e:
		frappe.log_error(
			message=str(e),
			title="Wishlist Availability Check Task Failed"
		)


def reconcile_social_proof_counters():
	"""
	Daily at 03:00: Recount all social proof counters from source data.

	Reconciles potentially drifted counters by recalculating from the actual
	Quick Favorite and User Wishlist records. Counters can drift due to
	failed transactions, race conditions, or manual data changes.

	Counter Fields:
	- Product.wishlist_count: Count of Wishlist Items referencing this product
	- Product.favorite_count: Count of Quick Favorites targeting this product
	- Seller Profile.favorite_count: Count of Quick Favorites targeting this seller
	- Seller Profile.total_wishlist_count: Sum of wishlist_count across all seller's listings
	- Seller Store.favorite_count: Count of Quick Favorites targeting this store
	- Listing.wishlist_count: Count of Quick Favorites targeting this listing
	"""
	frappe.logger("tradehub_catalog").info(
		"Running reconcile_social_proof_counters scheduled task"
	)

	try:
		reconciled = 0
		errors = 0

		# 1. Reconcile Product.favorite_count from Quick Favorites
		reconciled += _reconcile_favorite_count("Product", "favorite_count")

		# 2. Reconcile Product.wishlist_count from Wishlist Items
		reconciled += _reconcile_product_wishlist_count()

		# 3. Reconcile Seller Profile.favorite_count from Quick Favorites
		reconciled += _reconcile_favorite_count("Seller Profile", "favorite_count")

		# 4. Reconcile Seller Store.favorite_count from Quick Favorites
		reconciled += _reconcile_favorite_count("Seller Store", "favorite_count")

		# 5. Reconcile Listing.wishlist_count from Quick Favorites
		reconciled += _reconcile_favorite_count("Listing", "wishlist_count")

		# 6. Reconcile Seller Profile.total_wishlist_count
		reconciled += _reconcile_seller_total_wishlist_count()

		frappe.db.commit()

		frappe.logger("tradehub_catalog").info(
			f"Social proof counter reconciliation completed: {reconciled} records updated"
		)

	except Exception as e:
		frappe.log_error(
			message=str(e),
			title="Social Proof Reconciliation Task Failed"
		)


def send_price_drop_digest():
	"""
	Daily at 09:00: Send digest emails to users with digest_mode=1.

	Aggregates all price changes for a user's wishlist items and sends
	a single digest email instead of individual notifications.

	Business Rules:
	- Only send to users with digest_mode=1 on their wishlist
	- Include only items with significant price drops (>= 5%)
	- Respect daily notification cap (10/day)
	- Skip users who have already received max daily notifications
	"""
	frappe.logger("tradehub_catalog").info(
		"Running send_price_drop_digest scheduled task"
	)

	try:
		# Get all wishlists with digest_mode enabled
		wishlists = frappe.get_all(
			"User Wishlist",
			filters={"digest_mode": 1},
			fields=["name", "user", "list_name"]
		)

		sent_count = 0
		error_count = 0

		for wishlist in wishlists:
			try:
				# Get items with significant price drops
				items_with_drops = _get_price_drop_items(wishlist.name)

				if not items_with_drops:
					continue

				from tradehub_catalog.tradehub_catalog.wishlist.notifications import (
					send_daily_digest,
				)

				sent = send_daily_digest(
					user=wishlist.user,
					wishlist_name=wishlist.list_name,
					items_with_changes=items_with_drops,
				)

				if sent:
					sent_count += 1

			except Exception as e:
				error_count += 1
				frappe.log_error(
					message=f"Failed to send digest to {wishlist.user}: {str(e)}",
					title="Wishlist Digest Error"
				)

		frappe.db.commit()

		frappe.logger("tradehub_catalog").info(
			f"Price drop digest completed: {sent_count} digests sent, "
			f"{error_count} errors"
		)

	except Exception as e:
		frappe.log_error(
			message=str(e),
			title="Price Drop Digest Task Failed"
		)


def cleanup_orphaned_favorites():
	"""
	Weekly: Remove Quick Favorites pointing to deleted targets.

	Quick Favorites use Dynamic Links to reference target documents.
	When a target (Product, Seller Profile, Seller Store, Listing)
	is deleted, the Quick Favorite becomes orphaned.

	This task finds and removes these orphaned records to maintain
	data integrity.

	Business Rules:
	- Process max 1000 orphans per run
	- Log a summary of cleanup actions
	"""
	frappe.logger("tradehub_catalog").info(
		"Running cleanup_orphaned_favorites scheduled task"
	)

	try:
		target_types = ["Product", "Seller Profile", "Seller Store", "Listing"]
		total_deleted = 0

		for target_type in target_types:
			try:
				deleted = _cleanup_orphans_for_type(target_type)
				total_deleted += deleted
			except Exception as e:
				frappe.log_error(
					message=f"Failed to cleanup orphaned favorites for {target_type}: {str(e)}",
					title="Orphan Cleanup Error"
				)

		frappe.db.commit()

		frappe.logger("tradehub_catalog").info(
			f"Orphaned favorites cleanup completed: {total_deleted} records removed"
		)

	except Exception as e:
		frappe.log_error(
			message=str(e),
			title="Orphan Cleanup Task Failed"
		)


# =============================================================================
# DOC EVENT HANDLERS
# =============================================================================


def on_wishlist_update(doc, method):
	"""
	Doc event handler for User Wishlist on_update.

	Updates product wishlist_count fields when wishlist items change.
	"""
	if not doc.items:
		return

	for item in doc.items:
		if item.product:
			_update_product_wishlist_count(item.product)


def on_wishlist_trash(doc, method):
	"""
	Doc event handler for User Wishlist on_trash.

	Decrements product wishlist_count fields when a wishlist is deleted.
	"""
	if not doc.items:
		return

	for item in doc.items:
		if item.product:
			_update_product_wishlist_count(item.product)


def on_favorite_insert(doc, method):
	"""
	Doc event handler for Quick Favorite after_insert.

	Counter management is handled in the Quick Favorite controller.
	This hook is for additional cross-cutting concerns like logging.
	"""
	frappe.logger("tradehub_catalog").debug(
		f"Quick Favorite created: {doc.user} -> {doc.target_type}/{doc.target_reference}"
	)


def on_favorite_trash(doc, method):
	"""
	Doc event handler for Quick Favorite on_trash.

	Counter management is handled in the Quick Favorite controller.
	This hook is for additional cross-cutting concerns like logging.
	"""
	frappe.logger("tradehub_catalog").debug(
		f"Quick Favorite deleted: {doc.user} -> {doc.target_type}/{doc.target_reference}"
	)


# =============================================================================
# INTERNAL HELPERS
# =============================================================================


def _update_item_price(item):
	"""
	Update current_price and price_change_pct for a single wishlist item.

	Args:
		item: Dict with item_name, listing, added_price, listing_price
	"""
	listing_price = flt(item.listing_price)

	if listing_price <= 0:
		return

	added_price = flt(item.added_price)
	old_price = flt(item.old_current_price)

	# Calculate price change percentage relative to added_price
	price_change_pct = 0.0
	if added_price > 0:
		price_change_pct = round(
			((listing_price - added_price) / added_price) * 100, 2
		)

	# Only update if price actually changed
	if listing_price != old_price:
		frappe.db.set_value(
			"Wishlist Item",
			item.item_name,
			{
				"current_price": listing_price,
				"price_change_pct": price_change_pct,
			},
			update_modified=False,
		)


def _reconcile_favorite_count(target_type, counter_field):
	"""
	Reconcile favorite/wishlist counter for a target DocType.

	Counts actual Quick Favorites per target and updates the counter field.

	Args:
		target_type: DocType name (Product, Seller Profile, etc.)
		counter_field: Field name on the target DocType (favorite_count, wishlist_count)

	Returns:
		int: Number of records updated
	"""
	updated = 0

	# Get actual counts from Quick Favorites
	actual_counts = frappe.db.sql("""
		SELECT target_reference, COUNT(*) AS cnt
		FROM `tabQuick Favorite`
		WHERE target_type = %s
		GROUP BY target_reference
	""", target_type, as_dict=True)

	count_map = {row.target_reference: cint(row.cnt) for row in actual_counts}

	# Get all targets with their current counter values
	table_name = f"tab{target_type}"
	targets = frappe.db.sql(
		f"SELECT name, `{counter_field}` AS current_count FROM `{table_name}`",
		as_dict=True,
	)

	for target in targets:
		expected_count = count_map.get(target.name, 0)
		if cint(target.current_count) != expected_count:
			frappe.db.set_value(
				target_type,
				target.name,
				counter_field,
				expected_count,
				update_modified=False,
			)
			updated += 1

	return updated


def _reconcile_product_wishlist_count():
	"""
	Reconcile Product.wishlist_count from Wishlist Items.

	Counts actual Wishlist Items referencing each product.

	Returns:
		int: Number of records updated
	"""
	updated = 0

	actual_counts = frappe.db.sql("""
		SELECT wi.product, COUNT(*) AS cnt
		FROM `tabWishlist Item` wi
		JOIN `tabUser Wishlist` uw ON uw.name = wi.parent
		WHERE wi.product IS NOT NULL AND wi.product != ''
		GROUP BY wi.product
	""", as_dict=True)

	count_map = {row.product: cint(row.cnt) for row in actual_counts}

	products = frappe.db.sql(
		"SELECT name, wishlist_count FROM `tabProduct`",
		as_dict=True,
	)

	for product in products:
		expected_count = count_map.get(product.name, 0)
		if cint(product.wishlist_count) != expected_count:
			frappe.db.set_value(
				"Product",
				product.name,
				"wishlist_count",
				expected_count,
				update_modified=False,
			)
			updated += 1

	return updated


def _reconcile_seller_total_wishlist_count():
	"""
	Reconcile Seller Profile.total_wishlist_count.

	Sums wishlist_count across all listings belonging to each seller profile.

	Returns:
		int: Number of records updated
	"""
	updated = 0

	actual_counts = frappe.db.sql("""
		SELECT seller_profile, SUM(COALESCE(wishlist_count, 0)) AS total_count
		FROM `tabListing`
		WHERE seller_profile IS NOT NULL AND seller_profile != ''
		GROUP BY seller_profile
	""", as_dict=True)

	count_map = {row.seller_profile: cint(row.total_count) for row in actual_counts}

	sellers = frappe.db.sql(
		"SELECT name, total_wishlist_count FROM `tabSeller Profile`",
		as_dict=True,
	)

	for seller in sellers:
		expected_count = count_map.get(seller.name, 0)
		if cint(seller.total_wishlist_count) != expected_count:
			frappe.db.set_value(
				"Seller Profile",
				seller.name,
				"total_wishlist_count",
				expected_count,
				update_modified=False,
			)
			updated += 1

	return updated


def _get_price_drop_items(wishlist_name):
	"""
	Get wishlist items with significant price drops for digest.

	Args:
		wishlist_name: Name of the User Wishlist document

	Returns:
		list: List of dicts with item details and price change info
	"""
	from tradehub_catalog.tradehub_catalog.wishlist.notifications import (
		MIN_PRICE_DROP_PCT,
	)

	items = frappe.db.sql("""
		SELECT
			wi.product,
			wi.added_price,
			wi.current_price,
			wi.price_change_pct,
			p.product_name
		FROM `tabWishlist Item` wi
		LEFT JOIN `tabProduct` p ON p.name = wi.product
		WHERE wi.parent = %s
			AND wi.added_price > 0
			AND wi.current_price > 0
			AND wi.current_price < wi.added_price
			AND wi.notification_enabled = 1
	""", wishlist_name, as_dict=True)

	result = []
	for item in items:
		drop_pct = abs(flt(item.price_change_pct))
		if drop_pct >= MIN_PRICE_DROP_PCT:
			result.append({
				"item_name": item.product_name or item.product,
				"product": item.product,
				"added_price": flt(item.added_price, 2),
				"current_price": flt(item.current_price, 2),
				"drop_pct": round(drop_pct, 1),
				"drop_amount": flt(flt(item.added_price) - flt(item.current_price), 2),
			})

	return result


def _cleanup_orphans_for_type(target_type):
	"""
	Remove Quick Favorites pointing to deleted targets of a specific type.

	Args:
		target_type: DocType name (Product, Seller Profile, etc.)

	Returns:
		int: Number of orphaned records deleted
	"""
	table_name = f"tab{target_type}"

	# Find orphaned favorites where target no longer exists
	orphans = frappe.db.sql("""
		SELECT qf.name
		FROM `tabQuick Favorite` qf
		LEFT JOIN `{table}` t ON t.name = qf.target_reference
		WHERE qf.target_type = %s
			AND t.name IS NULL
		LIMIT 1000
	""".format(table=table_name), target_type, as_dict=True)

	deleted = 0
	for orphan in orphans:
		try:
			frappe.delete_doc(
				"Quick Favorite", orphan.name,
				ignore_permissions=True,
				force=True,
			)
			deleted += 1
		except Exception as e:
			frappe.log_error(
				message=f"Failed to delete orphaned favorite {orphan.name}: {str(e)}",
				title="Orphan Cleanup Error"
			)

	return deleted


def _update_product_wishlist_count(product_name):
	"""
	Recalculate wishlist_count for a single product.

	Args:
		product_name: Name of the Product document
	"""
	if not frappe.db.exists("Product", product_name):
		return

	count = frappe.db.count(
		"Wishlist Item",
		filters={"product": product_name}
	)

	frappe.db.set_value(
		"Product",
		product_name,
		"wishlist_count",
		cint(count),
		update_modified=False,
	)
