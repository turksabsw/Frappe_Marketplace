# Copyright (c) 2024, TR TradeHub and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import getdate, nowdate


class SellerCertificate(Document):
	"""
	Seller Certificate - Child table for seller certificates.

	Tracks certificates held by sellers including type, validity dates,
	and verification status.
	"""

	def validate(self):
		"""Validate the certificate entry"""
		self.validate_dates()
		self.update_verification_status()

	def validate_dates(self):
		"""Validate issue date is before expiry date"""
		if self.issue_date and self.expiry_date:
			if getdate(self.expiry_date) < getdate(self.issue_date):
				frappe.throw(
					_("Row {0}: Expiry Date cannot be before Issue Date").format(self.idx)
				)

	def update_verification_status(self):
		"""Auto-set status to Expired if expiry date has passed"""
		if self.expiry_date and getdate(self.expiry_date) < getdate(nowdate()):
			self.verification_status = "Expired"
