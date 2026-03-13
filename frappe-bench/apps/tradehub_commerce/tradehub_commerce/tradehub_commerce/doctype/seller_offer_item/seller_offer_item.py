# Copyright (c) 2026, TR TradeHub and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class SellerOfferItem(Document):
	def validate(self):
		self.total_price = (self.offered_quantity or 0) * (self.unit_price or 0)
