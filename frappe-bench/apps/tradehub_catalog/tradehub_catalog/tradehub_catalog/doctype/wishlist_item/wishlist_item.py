# Copyright (c) 2026, TR TradeHub and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class WishlistItem(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		added_at: DF.Datetime
		added_price: DF.Currency
		current_price: DF.Currency
		listing: DF.Link
		notes: DF.SmallText
		notification_enabled: DF.Check
		parent: DF.Data
		parentfield: DF.Data
		parenttype: DF.Data
		price_change_pct: DF.Percent
		priority: DF.Literal["Low", "Medium", "High"]
		product: DF.Link
		seller_store: DF.Link
		target_price: DF.Currency
	# end: auto-generated types

	pass
