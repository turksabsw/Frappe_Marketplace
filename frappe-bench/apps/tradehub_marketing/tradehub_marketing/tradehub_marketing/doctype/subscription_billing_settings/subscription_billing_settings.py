# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class SubscriptionBillingSettings(Document):
	"""
	Subscription Billing Settings Single DocType for TR-TradeHub.

	Global configuration for subscription billing lifecycle,
	grace periods, renewal retries, and reminder schedules.
	"""

	def validate(self):
		"""Validate settings values."""
		self.validate_non_negative_integers()

	def validate_non_negative_integers(self):
		"""Ensure numeric settings are non-negative."""
		int_fields = [
			"grace_period_days",
			"past_due_to_grace_days",
			"auto_cancel_after_suspension_days",
			"max_renewal_retries",
		]
		for field in int_fields:
			value = self.get(field)
			if value is not None and value < 0:
				frappe.throw(
					_("{0} must be a non-negative integer.").format(
						self.meta.get_label(field)
					)
				)
