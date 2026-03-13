# Copyright (c) 2026, TR TradeHub and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import nowdate

from tradehub_commerce.tradehub_commerce.utils.commission_utils import (
	invalidate_commission_cache,
)


class TRTradeHubSettings(Document):
	"""
	TR TradeHub Settings Single DocType.

	Stores global configuration for the TR TradeHub platform,
	including commission calculation toggle and related settings.
	"""

	def on_update(self):
		"""Handle settings update, particularly commission toggle changes."""
		self._handle_commission_toggle()

	def _handle_commission_toggle(self):
		"""Detect and process commission_enabled field changes."""
		doc_before_save = self.get_doc_before_save()

		if not doc_before_save:
			return

		old_value = int(doc_before_save.commission_enabled or 0)
		new_value = int(self.commission_enabled or 0)

		if old_value == new_value:
			return

		logger = frappe.logger("commission")
		current_date = nowdate()

		# Invalidate commission cache immediately
		invalidate_commission_cache()

		if new_value:
			# Commission was ENABLED
			frappe.db.set_single_value(
				"TR TradeHub Settings", "commission_enabled_date", current_date
			)
			logger.info(
				"Commission calculation ENABLED on %s by %s",
				current_date,
				frappe.session.user,
			)

			if self.commission_enable_notify_sellers:
				frappe.enqueue(
					"tr_tradehub.tr_tradehub.doctype.tr_tradehub_settings"
					".tr_tradehub_settings.notify_sellers_commission_enabled",
					queue="default",
				)
		else:
			# Commission was DISABLED
			frappe.db.set_single_value(
				"TR TradeHub Settings", "commission_disabled_date", current_date
			)
			logger.info(
				"Commission calculation DISABLED on %s by %s",
				current_date,
				frappe.session.user,
			)

			if self.commission_enable_notify_sellers:
				frappe.enqueue(
					"tr_tradehub.tr_tradehub.doctype.tr_tradehub_settings"
					".tr_tradehub_settings.notify_sellers_commission_disabled",
					queue="default",
				)


def notify_sellers_commission_enabled():
	"""Notify all active sellers that commission has been re-enabled.

	Enqueued as a background job when the commission toggle is turned ON
	and commission_enable_notify_sellers is checked.
	"""
	_notify_sellers(
		event="commission_enabled",
		subject=_("Commission Calculation Enabled"),
		message=_(
			"Commission calculation has been re-enabled on the platform. "
			"Standard commission rates now apply to all transactions."
		),
	)


def notify_sellers_commission_disabled():
	"""Notify all active sellers that commission has been disabled.

	Enqueued as a background job when the commission toggle is turned OFF
	and commission_enable_notify_sellers is checked.
	"""
	_notify_sellers(
		event="commission_disabled",
		subject=_("Commission Calculation Disabled"),
		message=_(
			"Commission calculation has been temporarily disabled on the platform. "
			"No commission will be deducted from your transactions until further notice."
		),
	)


def _notify_sellers(event, subject, message):
	"""Send notification to all active sellers about commission status change.

	Args:
		event: The realtime event name to publish.
		subject: Notification subject text.
		message: Notification body text.
	"""
	logger = frappe.logger("commission")

	sellers = frappe.get_all(
		"Seller Profile",
		filters={"status": "Active"},
		fields=["name", "user"],
	)

	notified_count = 0

	for seller in sellers:
		if not seller.user:
			continue

		try:
			frappe.publish_realtime(
				event,
				{"message": message, "subject": subject},
				user=seller.user,
			)
			notified_count += 1
		except Exception as e:
			frappe.log_error(
				f"Failed to notify seller {seller.name}: {str(e)}",
				"Commission Toggle Notification Error",
			)

	logger.info(
		"Commission toggle notification (%s) sent to %d sellers",
		event,
		notified_count,
	)
