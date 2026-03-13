# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ContractCenterSettings(Document):
	"""
	Contract Center Settings Single DocType for TR-TradeHub.

	Global configuration for contract management, consent workflows,
	e-signature settings, and bulk signing options.
	"""

	def validate(self):
		"""Validate settings values."""
		self.validate_positive_integers()

	def validate_positive_integers(self):
		"""Ensure numeric settings are non-negative."""
		int_fields = [
			"reacceptance_grace_days",
		]
		for field in int_fields:
			value = self.get(field)
			if value is not None and value < 0:
				frappe.throw(
					_("{0} must be a non-negative integer.").format(
						self.meta.get_label(field)
					)
				)
