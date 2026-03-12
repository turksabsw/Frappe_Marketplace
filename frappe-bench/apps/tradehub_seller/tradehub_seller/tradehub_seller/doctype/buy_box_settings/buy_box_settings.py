# Copyright (c) 2026, Trade Hub and contributors
# For license information, please see license.txt

"""
Buy Box Settings Single DocType for Trade Hub B2B Marketplace.

This module configures the Buy Box scoring algorithm parameters including
scoring weights, tier bonuses, and recalculation settings.

Key features:
- Configurable weights for 6 scoring criteria (price, delivery, rating, stock, service, tier)
- Validation that all weights sum to exactly 1.0
- Tier bonus configuration via child table
- Algorithm tuning parameters (cooldown, min orders, batch size)
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class BuyBoxSettings(Document):
	"""
	Buy Box Settings Single DocType.

	Configures the weighted scoring algorithm used to determine
	Buy Box winners across the marketplace.
	"""

	def validate(self):
		"""Validate settings before saving."""
		self.calculate_total_weight()
		self.validate_weights_sum()
		self.validate_individual_weights()
		self.validate_algorithm_settings()

	def calculate_total_weight(self):
		"""Calculate and set the total weight from all individual weights."""
		self.total_weight = flt(
			flt(self.price_weight) +
			flt(self.delivery_weight) +
			flt(self.rating_weight) +
			flt(self.stock_weight) +
			flt(self.service_weight) +
			flt(self.tier_weight),
			precision=2
		)

	def validate_weights_sum(self):
		"""Validate that all weights sum to exactly 1.0."""
		if abs(flt(self.total_weight) - 1.0) > 0.001:
			frappe.throw(
				_("Scoring weights must sum to 1.0. Current total: {0}").format(
					self.total_weight
				)
			)

	def validate_individual_weights(self):
		"""Validate that each weight is between 0 and 1."""
		weight_fields = [
			("price_weight", "Price Weight"),
			("delivery_weight", "Delivery Weight"),
			("rating_weight", "Rating Weight"),
			("stock_weight", "Stock Weight"),
			("service_weight", "Service Weight"),
			("tier_weight", "Tier Weight"),
		]

		for fieldname, label in weight_fields:
			value = flt(getattr(self, fieldname, 0))
			if value < 0 or value > 1:
				frappe.throw(
					_("{0} must be between 0 and 1").format(label)
				)

	def validate_algorithm_settings(self):
		"""Validate algorithm configuration values."""
		if self.cooldown_seconds is not None and int(self.cooldown_seconds or 0) < 0:
			frappe.throw(_("Cooldown Seconds cannot be negative"))

		if self.min_orders_for_metrics is not None and int(self.min_orders_for_metrics or 0) < 0:
			frappe.throw(_("Min Orders for Metrics cannot be negative"))

		if self.recalculation_batch_size is not None and int(self.recalculation_batch_size or 0) <= 0:
			frappe.throw(_("Recalculation Batch Size must be greater than zero"))
