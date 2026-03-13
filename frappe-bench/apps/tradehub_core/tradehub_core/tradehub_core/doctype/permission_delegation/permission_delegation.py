# Copyright (c) 2026, TR TradeHub and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import date_diff, getdate


# Maximum delegation duration in days
MAX_DELEGATION_DAYS = 90

# Roles that cannot be delegated
RESTRICTED_ROLES = ["System Manager"]


class PermissionDelegation(Document):
	"""
	Permission Delegation DocType for temporary role delegation.

	Allows users to temporarily delegate their roles to another user:
	- Maximum duration of 90 days
	- System Manager role cannot be delegated
	- Requires manager/admin approval
	- Supports revocation at any time
	- Tenant-scoped for multi-tenant isolation
	"""

	def validate(self):
		self._validate_delegator_not_delegatee()
		self._validate_no_restricted_roles()
		self._validate_date_range()
		self._validate_max_duration()

	def _validate_delegator_not_delegatee(self):
		"""Ensure a user cannot delegate permissions to themselves."""
		if self.delegator == self.delegatee:
			frappe.throw(
				_("Delegator and Delegatee cannot be the same user"),
				frappe.ValidationError
			)

	def _validate_no_restricted_roles(self):
		"""Ensure restricted roles (e.g., System Manager) are not delegated."""
		if not self.delegated_roles:
			return

		roles = [r.strip() for r in self.delegated_roles.split(",") if r.strip()]

		for role in roles:
			if role in RESTRICTED_ROLES:
				frappe.throw(
					_("Role '{0}' cannot be delegated").format(role),
					frappe.ValidationError
				)

	def _validate_date_range(self):
		"""Ensure start_date is before end_date."""
		if not self.start_date or not self.end_date:
			return

		if getdate(self.start_date) > getdate(self.end_date):
			frappe.throw(
				_("Start Date must be before End Date"),
				frappe.ValidationError
			)

	def _validate_max_duration(self):
		"""Ensure delegation duration does not exceed 90 days."""
		if not self.start_date or not self.end_date:
			return

		duration = date_diff(self.end_date, self.start_date)

		if duration > MAX_DELEGATION_DAYS:
			frappe.throw(
				_("Delegation duration cannot exceed {0} days. Current duration: {1} days").format(
					MAX_DELEGATION_DAYS, duration
				),
				frappe.ValidationError
			)
