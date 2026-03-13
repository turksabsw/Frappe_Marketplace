# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ContractCompiledOutput(Document):
	"""
	Contract Compiled Output DocType for TR-TradeHub.

	Stores the immutable compiled output of a contract template after
	rule-based clause evaluation. Once created, records cannot be
	modified or deleted to preserve audit integrity.
	"""

	def before_save(self):
		"""Enforce immutability — only new documents may be saved."""
		if not self.is_new():
			frappe.throw(
				_("Contract Compiled Output records are immutable and cannot be modified.")
			)

	def on_trash(self):
		"""Prevent deletion of compiled output records."""
		frappe.throw(
			_("Contract Compiled Output records cannot be deleted.")
		)

	def before_insert(self):
		"""Set default values before creating a new compiled output."""
		if not self.compiled_by:
			self.compiled_by = frappe.session.user
