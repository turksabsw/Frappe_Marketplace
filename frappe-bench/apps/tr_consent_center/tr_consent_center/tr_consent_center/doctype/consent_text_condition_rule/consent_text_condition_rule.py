# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ConsentTextConditionRule(Document):
	"""Consent Text Condition Rule child table for defining dynamic consent clause rules."""

	def validate(self):
		"""Validate rule data."""
		self.validate_between_operator()

	def validate_between_operator(self):
		"""Validate that 'between' operator has two comma-separated values."""
		if self.condition_operator == "between" and self.condition_value:
			values = [v.strip() for v in self.condition_value.split(",") if v.strip()]
			if len(values) != 2:
				frappe.throw(
					_("'between' operator requires exactly two comma-separated values, got {0}").format(
						len(values)
					)
				)
			# Validate both values are numeric for range comparison
			for val in values:
				try:
					float(val)
				except ValueError:
					frappe.throw(
						_("'between' operator requires numeric values, got '{0}'").format(val)
					)

	def evaluate_condition(self, context):
		"""
		Evaluate this condition rule against the given context.

		Args:
			context (dict): Dictionary containing context values to evaluate against.
				Example: {"package": "Premium", "seller_type": "Manufacturer"}

		Returns:
			bool: True if condition is met, False otherwise.
		"""
		if not self.is_active:
			return False

		if not self.condition_type or not self.condition_operator or not self.condition_value:
			return False

		actual_value = context.get(self.condition_type)

		if actual_value is None:
			return False

		expected_value = self.condition_value

		if self.condition_operator == "equals":
			return str(actual_value).lower() == str(expected_value).lower()
		elif self.condition_operator == "not_equals":
			return str(actual_value).lower() != str(expected_value).lower()
		elif self.condition_operator == "in":
			values = [v.strip().lower() for v in expected_value.split(",")]
			return str(actual_value).lower() in values
		elif self.condition_operator == "not_in":
			values = [v.strip().lower() for v in expected_value.split(",")]
			return str(actual_value).lower() not in values
		elif self.condition_operator == "greater_than":
			try:
				return float(actual_value) > float(expected_value)
			except (ValueError, TypeError):
				return False
		elif self.condition_operator == "less_than":
			try:
				return float(actual_value) < float(expected_value)
			except (ValueError, TypeError):
				return False
		elif self.condition_operator == "between":
			try:
				values = [float(v.strip()) for v in expected_value.split(",")]
				if len(values) != 2:
					return False
				return values[0] <= float(actual_value) <= values[1]
			except (ValueError, TypeError):
				return False
		elif self.condition_operator == "contains":
			return str(expected_value).lower() in str(actual_value).lower()

		return False
