# Copyright (c) 2026, Trade Hub and contributors
# For license information, please see license.txt

"""
Buy Box Settings Single DocType for Trade Hub B2B Marketplace.

This module configures the Buy Box scoring algorithm parameters including
scoring weights, tier bonuses, and recalculation settings.

Key features:
- Configurable weights for 6 scoring criteria (price, delivery, rating, stock, service, tier)
- Auto-normalization when weights do not sum to exactly 1.0
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
		self.validate_individual_weights()
		self.calculate_total_weight()
		self.normalize_weights()
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
			precision=6
		)

	def normalize_weights(self):
		"""
		Auto-normalize weights if they do not sum to 1.0.

		Instead of throwing an error, proportionally adjusts all weights
		so they sum to exactly 1.0. Notifies the user when normalization occurs.
		"""
		if abs(flt(self.total_weight) - 1.0) <= 0.001:
			# Already sums to 1.0 within tolerance
			self.total_weight = flt(1.0, precision=2)
			return

		if flt(self.total_weight) <= 0:
			frappe.throw(
				_("At least one scoring weight must be greater than zero")
			)

		# Auto-normalize: divide each weight by the total sum
		total = flt(self.total_weight)
		original_total = total

		weight_fields = [
			"price_weight", "delivery_weight", "rating_weight",
			"stock_weight", "service_weight", "tier_weight",
		]

		for fieldname in weight_fields:
			value = flt(getattr(self, fieldname, 0))
			normalized = flt(value / total, precision=6)
			setattr(self, fieldname, normalized)

		# Recalculate total after normalization
		self.calculate_total_weight()
		self.total_weight = flt(1.0, precision=2)

		frappe.msgprint(
			_("Scoring weights were auto-normalized from total {0} to 1.0").format(
				flt(original_total, precision=4)
			),
			indicator="blue",
			alert=True
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
			if value < 0:
				frappe.throw(
					_("{0} cannot be negative").format(label)
				)

	def validate_algorithm_settings(self):
		"""Validate algorithm configuration values."""
		if self.cooldown_seconds is not None and int(self.cooldown_seconds or 0) < 0:
			frappe.throw(_("Cooldown Seconds cannot be negative"))

		if self.min_orders_for_metrics is not None and int(self.min_orders_for_metrics or 0) < 0:
			frappe.throw(_("Min Orders for Metrics cannot be negative"))

		if self.recalculation_batch_size is not None and int(self.recalculation_batch_size or 0) <= 0:
			frappe.throw(_("Recalculation Batch Size must be greater than zero"))
