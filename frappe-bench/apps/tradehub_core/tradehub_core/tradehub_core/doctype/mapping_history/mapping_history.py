# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime


class MappingHistory(Document):
	"""
	Mapping History DocType for tracking previously confirmed column mappings.

	Records the historical mapping between source columns (from import files)
	and target fieldnames (in DocTypes), per tenant/seller context. Used by
	the auto-match algorithm to provide P0 (Historical) priority matches
	with 100% confidence.
	"""

	def validate(self):
		self._guard_required_fields()
		self._normalize_source_column()
		self._set_defaults()

	def _guard_required_fields(self):
		"""Ensure required fields are populated."""
		if not self.source_column:
			frappe.throw(_("Source Column is required"))
		if not self.target_fieldname:
			frappe.throw(_("Target Fieldname is required"))
		if not self.target_doctype:
			frappe.throw(_("Target DocType is required"))

	def _normalize_source_column(self):
		"""Generate normalized version of source column for matching."""
		if self.source_column and not self.source_column_normalized:
			self.source_column_normalized = self._normalize_turkish(self.source_column)

	def _set_defaults(self):
		"""Set default values."""
		if not self.confirmation_count:
			self.confirmation_count = 1
		if not self.last_confirmed:
			self.last_confirmed = now_datetime()

	@staticmethod
	def _normalize_turkish(text):
		"""
		Normalize text with Turkish-specific character handling.

		Handles Turkish I/İ/ı/i mapping correctly:
		- İ → i (Turkish capital I with dot → lowercase i)
		- I → ı (Turkish capital I without dot → lowercase ı)
		- ı → ı (Turkish lowercase dotless i stays)
		- i → i (regular lowercase i stays)
		"""
		if not text:
			return ""

		# Turkish-specific lowercase mapping
		turkish_map = str.maketrans({
			"İ": "i",
			"I": "ı",
			"Ş": "ş",
			"Ç": "ç",
			"Ğ": "ğ",
			"Ö": "ö",
			"Ü": "ü",
		})

		result = text.translate(turkish_map).lower()
		# Remove extra whitespace, underscores, hyphens for normalization
		result = result.strip().replace("_", " ").replace("-", " ")
		# Collapse multiple spaces
		result = " ".join(result.split())
		return result

	def increment_confirmation(self):
		"""Increment the confirmation count and update last confirmed timestamp."""
		self.confirmation_count = (self.confirmation_count or 0) + 1
		self.last_confirmed = now_datetime()
		self.save()
