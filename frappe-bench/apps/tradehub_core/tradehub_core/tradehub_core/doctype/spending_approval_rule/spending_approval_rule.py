# Copyright (c) 2026, TR TradeHub and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class SpendingApprovalRule(Document):
	"""
	Spending Approval Rule DocType for ABAC spending limit controls.

	Defines approval chains based on transaction amounts:
	- Maps roles to approver roles for specific spending ranges
	- Supports single, dual, and committee approval types
	- Tenant-scoped for multi-tenant isolation
	"""

	def validate(self):
		self._validate_amount_range()
		self._validate_no_overlapping_rules()

	def _validate_amount_range(self):
		"""Ensure min_amount is less than max_amount."""
		if flt(self.min_amount) < 0:
			frappe.throw(
				_("Minimum Amount cannot be negative"),
				frappe.ValidationError
			)

		if flt(self.max_amount) <= 0:
			frappe.throw(
				_("Maximum Amount must be greater than zero"),
				frappe.ValidationError
			)

		if flt(self.min_amount) >= flt(self.max_amount):
			frappe.throw(
				_("Minimum Amount must be less than Maximum Amount"),
				frappe.ValidationError
			)

	def _validate_no_overlapping_rules(self):
		"""Check for overlapping spending rules for the same role, tenant, and currency."""
		filters = {
			"role": self.role,
			"currency": self.currency,
			"is_active": 1,
			"name": ["!=", self.name]
		}

		if self.tenant:
			filters["tenant"] = self.tenant
		else:
			filters["tenant"] = ["is", "not set"]

		existing_rules = frappe.get_all(
			"Spending Approval Rule",
			filters=filters,
			fields=["name", "min_amount", "max_amount"]
		)

		for rule in existing_rules:
			if (
				flt(self.min_amount) < flt(rule.max_amount)
				and flt(self.max_amount) > flt(rule.min_amount)
			):
				frappe.throw(
					_("Spending range {0}-{1} overlaps with existing rule {2} ({3}-{4})").format(
						self.min_amount, self.max_amount,
						rule.name, rule.min_amount, rule.max_amount
					),
					frappe.ValidationError
				)
