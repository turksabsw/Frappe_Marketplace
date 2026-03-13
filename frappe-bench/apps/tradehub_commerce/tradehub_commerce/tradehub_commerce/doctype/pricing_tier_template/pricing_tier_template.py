# Copyright (c) 2026, TR TradeHub and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, cint


class PricingTierTemplate(Document):
	"""
	Pricing Tier Template DocType for managing quantity-based pricing tiers.

	Manages reusable pricing tier configurations including:
	- Template identification and categorization
	- Quantity-based tier definitions with discount percentages
	- Default template management (only one allowed)
	"""

	def validate(self):
		"""Validate pricing tier template data before saving."""
		self.validate_tiers()
		self.validate_default_template()

	def validate_tiers(self):
		"""Validate pricing tiers for ascending min_quantity and valid discount percentages."""
		if not self.tiers:
			return

		# Validate discount_percentage is between 0 and 100
		for tier in self.tiers:
			if flt(tier.discount_percentage) < 0 or flt(tier.discount_percentage) > 100:
				frappe.throw(
					_("Discount percentage for tier '{0}' must be between 0 and 100").format(
						tier.tier_label or tier.idx
					)
				)

		# Validate ascending min_quantity with no overlaps
		sorted_tiers = sorted(self.tiers, key=lambda t: flt(t.min_quantity))
		for i in range(1, len(sorted_tiers)):
			current_min = flt(sorted_tiers[i].min_quantity)
			previous_min = flt(sorted_tiers[i - 1].min_quantity)

			if current_min <= previous_min:
				frappe.throw(
					_("Tier '{0}' has min_quantity {1} which must be greater than "
					  "tier '{2}' min_quantity {3}. Tiers must have ascending min_quantity values.").format(
						sorted_tiers[i].tier_label or sorted_tiers[i].idx,
						current_min,
						sorted_tiers[i - 1].tier_label or sorted_tiers[i - 1].idx,
						previous_min
					)
				)

	def validate_default_template(self):
		"""Ensure only one is_default=1 template exists."""
		if not cint(self.is_default):
			return

		existing_default = frappe.db.get_value(
			"Pricing Tier Template",
			{
				"is_default": 1,
				"name": ["!=", self.name]
			},
			"name"
		)

		if existing_default:
			frappe.db.set_value("Pricing Tier Template", existing_default, "is_default", 0)
			frappe.msgprint(
				_("Previous default template '{0}' has been unset").format(existing_default),
				indicator="blue"
			)
